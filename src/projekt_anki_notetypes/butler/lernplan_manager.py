from aqt import mw
from aqt.operations import CollectionOp
from aqt.qt import *
from aqt.utils import showWarning, tooltip

from ..constants import ADDON_DIR_NAME
from .lernplan_decks import (
    LERNTAG_PREFIX,
    DeckResult,
    LerntagSettings,
    effective_today,
    get_lerntag_list,
    rebuild_lernplan_decks,
    update_past_days,
)
from .utils import check_ankizin_installation

DEFAULT_WOCHENTAGE = [True] * 5 + [False] * 2


def _get_config() -> dict:
    """Get addon config or return empty dict if not configured."""
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    return conf if conf is not None else {}


def report_result(result: DeckResult, silent: bool = False) -> None:
    """Show failures (always) and decks without cards (unless silent). Main thread only."""
    if result.failed:
        showWarning("<br><br>".join(f"<b>{name}</b>: {msg}" for name, msg in result.failed))
    elif result.skipped and not silent:
        tooltip(f"{len(result.skipped)} Stapel ohne Karten wurden nicht erstellt (z.B. keine TOP-100/High-Yield Karten an diesem Tag).", period=5000)


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

    def _setup_lerntag_combo(
        self,
        layout: QLayout,
        lerntag: str,
        label_text: str = "<b>Lerntag:</b>",
    ) -> None:
        self.lerntag_combo_label = QLabel(label_text)
        layout.addWidget(self.lerntag_combo_label)
        self.lerntag_combo = QComboBox()
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        fixed_font.setPointSize(fixed_font.pointSize() + 2)
        self.lerntag_combo.setFont(fixed_font)
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
            lerntag=(self.lerntag_combo.currentData() or "001").zfill(3),
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
        if not self.lerntag_combo.count():
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

        past_days_info_label = QLabel("<i>Lerntage werden automatisch in den Verlaufsliste aufgenommen, sobald der Lernplan-Manager <b>automatisch</b> zu einem neuen Lerntag wechselt.</i>")
        past_days_info_label.setWordWrap(True)
        right_layout.addWidget(past_days_info_label)

        right_layout.addSpacing(10)

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
        self._setup_lerntag_combo(settings_layout, self._lerntag, label_text="<b>Aktueller Lerntag:</b>")
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

        manage_past_days_btn = QPushButton("Verlauf verwalten...")
        manage_past_days_btn.setFixedWidth(160)
        manage_past_days_btn.clicked.connect(self.open_past_days_dialog)
        buttons_layout.addWidget(manage_past_days_btn)

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

    def open_past_days_dialog(self):
        """Open the Past Days management dialog"""
        dialog = PastDaysDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            pass


class PastDaysDialog(QDialog):
    """Dialog to manage which past learning days are included in the past_days array"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Verlauf verwalten")
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # Explanation
        layout.addWidget(
            QLabel(
                "Hier kannst Du die Lerntage verwalten, die in Deinem Verlauf gespeichert sind.<br>"
                "Aktiviere oder deaktiviere einzelne Lerntage nach Bedarf."
            )
        )
        layout.addSpacing(10)

        # Scrollable list of past days
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)

        # Get the config to find past_days
        conf = _get_config()
        lernplan_conf = conf.get("lernplan", {})
        past_days = lernplan_conf.get("past_days", [])

        # Create checkboxes for each past day
        self.day_checkboxes = {}
        lerntag_list = get_lerntag_list(mw.col)
        lerntag_dict = {int(num): topic for num, topic in lerntag_list}
        row_texts = []

        # Show every lerntag in the plan and use past_days to preselect it.
        for day_idx, topic in sorted(lerntag_dict.items()):
            row_text = f"Lerntag <code>{str(day_idx).zfill(3)}</code> - {topic.replace('_', ' ')}"
            row_texts.append(row_text)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            checkbox = QCheckBox()
            checkbox.setChecked(day_idx < len(past_days) and past_days[day_idx])
            self.day_checkboxes[day_idx] = checkbox
            row_layout.addWidget(checkbox)

            label = QLabel(row_text)
            row_layout.addWidget(label)
            row_layout.addStretch()

            scroll_layout.addWidget(row_widget)

        # If no lerntage exist yet
        if not self.day_checkboxes:
            scroll_layout.addWidget(QLabel("<i>Keine Lerntage im Lernplan gefunden</i>"))

        # scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        if row_texts:
            label_font_metrics = QFontMetrics(self.font())
            widest_row = max(label_font_metrics.horizontalAdvance(text) for text in row_texts)
            checkbox_width = QCheckBox().sizeHint().width()
            chrome_width = 120
            target_width = widest_row + checkbox_width + chrome_width
            self.setMinimumWidth(target_width)
            self.resize(target_width, self.sizeHint().height())
        else:
            self.setMinimumWidth(500)

        # Buttons
        button_layout = QHBoxLayout()

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.save_and_close)
        button_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        button_layout.addStretch()
        
        reset_btn = QPushButton("Zurücksetzen")
        reset_btn.clicked.connect(self.reset_all)
        button_layout.addWidget(reset_btn)

        layout.addLayout(button_layout)

    def reset_all(self):
        """Reset all past days to False"""
        for checkbox in self.day_checkboxes.values():
            checkbox.setChecked(False)

    def save_and_close(self):
        """Save the checkbox states to config and close"""
        conf = _get_config()
        if "lernplan" not in conf:
            conf["lernplan"] = {}
        lernplan_conf = conf["lernplan"]

        past_days = lernplan_conf.get("past_days", [])

        # Update past_days based on checkbox states for every lerntag in the plan.
        for day_idx, checkbox in self.day_checkboxes.items():
            # Ensure array is large enough
            while len(past_days) <= day_idx:
                past_days.append(False)
            past_days[day_idx] = checkbox.isChecked()

        if self.day_checkboxes:
            max_day_idx = max(self.day_checkboxes)
            while len(past_days) <= max_day_idx:
                past_days.append(False)

        lernplan_conf["past_days"] = past_days
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)

        self.accept()


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
