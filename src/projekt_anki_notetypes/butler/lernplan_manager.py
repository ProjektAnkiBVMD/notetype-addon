import datetime
import re
from pathlib import Path

import anki
import aqt
from aqt import mw
from aqt.qt import *
from aqt.operations import CollectionOp
from anki.collection import OpChanges

from .utils import (
    check_ankizin_installation,
    create_filtered_deck,
    remove_filtered_deck,
)

ADDON_DIR_NAME = str(Path(__file__).parent.parent.name)


class LernplanManagerDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Lernplan-Manager (automatisch)")

        main_layout = QHBoxLayout(self)
        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        # Get the config
        conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
        if conf is None:
            lerntag = 0  # 0-indexed
            highyield_stark, highyield_leicht, normyield, lowyield = (
                False,
                False,
                True,
                False,
            )
            top100 = False
        else:
            lernplan_conf = conf.get("lernplan", {})
            # config contains e.g. "035" but we want 0-indexed
            lerntag = int(lernplan_conf.get("lerntag", "001")) - 1
            # Handle both old "highyield" and new separate options
            highyield_stark = lernplan_conf.get("highyield_stark", False)
            highyield_leicht = lernplan_conf.get("highyield_leicht", False)
            # For backward compatibility with old configs
            if (
                lernplan_conf.get("highyield", False)
                and not highyield_stark
                and not highyield_leicht
            ):
                highyield_stark = True
                highyield_leicht = True
            normyield = lernplan_conf.get("normyield", True)
            lowyield = lernplan_conf.get("lowyield", False)
            top100 = lernplan_conf.get("top100", False)
            autocreate = lernplan_conf.get("autocreate", False)
            autocreate_due = lernplan_conf.get("autocreate_due", True)
            autocreate_previous = lernplan_conf.get("autocreate_previous", False) # fmt: skip
            autocreate_no_previous = lernplan_conf.get("autocreate_no_previous", False) # fmt: skip
            wochentage = lernplan_conf.get("wochentage", [True] * 5 + [False] * 2) # fmt: skip

        # Logo
        logo_label = QLabel()
        logo_pixmap = QPixmap("icons:ankizin.png")
        logo_label.setPixmap(
            logo_pixmap.scaled(
                100,
                100,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        main_layout.addWidget(logo_label)

        # Right side layout
        right_layout = QVBoxLayout()

        # EXPLANATION
        right_layout.addWidget(
            QLabel(
                "Lass den <b>automatischen Lernplan-Manager</b> deine Lerntag-Auswahlstapel erstellen.<br>"
                "Du kannst wählen, ob nur TOP-100 Themen und/oder nur HIGH-YIELD Karten oder auch<br>normale und low-yield Karten enthalten sein sollen.<br>"
                "Der Lernplan-Manager erstellt jeden Tag automatisch einen neuen Lerntag-Auswahlstapel.<br>"
                "Alte Stapel werden automatisch aus der Übersicht entfernt, wenn sie nicht nach<br>!VORHERIGE LERNTAGE verschoben werden sollen.<br><br>"
                "Der Lernplan-Manager funktioniert am besten mit der aktuellsten Version von Ankizin<br>(aktuell: V4 / AnkiHub)."
            )
        )
        right_layout.addSpacing(20)

        # AUTOCREATE LERNTAG DECK
        right_layout.addWidget(QLabel("<b>Lernplan-Manager aktivieren:</b>"))
        self.autocreate_button = QCheckBox(
            "Lerntag-Auswahlstapel jeden Tag automatisch erstellen (empfohlen)"
        )
        self.autocreate_button.setChecked(autocreate)
        self.autocreate_button.setToolTip("Aktiviert den automatischen Lernplan-Manager.<br>Erstellt jeden Tag einen neuen Lerntag-Auswahlstapel <code>!LERNTAG&nbsp;XX</code>.")  # fmt: skip
        self.autocreate_button.toggled.connect(self.toggle_settings)
        right_layout.addWidget(self.autocreate_button)

        # CREATE FRAME TO HOLD SETTINGS
        self.settings_frame = QFrame()
        self.settings_frame.setVisible(autocreate)
        settings_layout = QVBoxLayout()
        settings_layout.setContentsMargins(0, 0, 0, 0)

        # WOCHENTAGE AUSWÄHLEN
        settings_layout.addSpacing(10)
        self.weekdays = QGroupBox("Wochentage für den Lernplan:")
        weekdays_layout = QHBoxLayout()
        self.weekday_buttons = []
        for weekday, check in zip(
            ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"], wochentage
        ):
            button = QCheckBox(weekday)
            button.setChecked(check)
            self.weekday_buttons.append(button)
            weekdays_layout.addWidget(button)
        self.weekdays.setLayout(weekdays_layout)
        settings_layout.addWidget(self.weekdays)

        # LERNTAG SELECTION MENU
        settings_layout.addSpacing(10)
        self.lerntag_combo_label = QLabel("<b>Aktueller Lerntag:</b>")
        settings_layout.addWidget(self.lerntag_combo_label)

        self.lerntag_combo = QComboBox()
        for number, topic in self.get_lerntag_list():
            display_text = f"{number} - {topic.replace('_', ' ')}"
            self.lerntag_combo.addItem(display_text, number)
        self.lerntag_combo.setCurrentIndex(lerntag)
        settings_layout.addWidget(self.lerntag_combo)

        # TOP-100 FILTER
        top100_group_box = QGroupBox()
        top100_buttons_layout = QVBoxLayout()
        top100_buttons_layout.setContentsMargins(5, 5, 5, 5)
        
        settings_layout.addSpacing(10)
        self.top100_button = QCheckBox("nur TOP-100 Themen")
        self.top100_button.setChecked(top100)
        self.top100_button.setToolTip(
            "Beschränkt die Auswahl auf die wichtigsten 100 Themen aus AMBOSS."
        )
        top100_buttons_layout.addWidget(self.top100_button)
        top100_group_box.setLayout(top100_buttons_layout)
        settings_layout.addWidget(top100_group_box)

        # YIELD SELECTION
        yield_group_box = QGroupBox()
        yield_buttons_layout = QVBoxLayout()
        yield_buttons_layout.setContentsMargins(5, 5, 5, 5)

        self.highyield_stark_button = QRadioButton(
            "nur HIGH-YIELD stark (stark gelb)"
        )
        self.highyield_stark_button.setChecked(
            highyield_stark and not highyield_leicht
        )
        yield_buttons_layout.addWidget(self.highyield_stark_button)

        self.highyield_all_button = QRadioButton(
            "alle HIGH-YIELD Karten (stark + leicht gelb)"
        )
        self.highyield_all_button.setChecked(
            highyield_stark and highyield_leicht
        )
        yield_buttons_layout.addWidget(self.highyield_all_button)

        self.standard_button = QRadioButton("STANDARD Karten (high-yield und normal)") # fmt: skip
        self.standard_button.setChecked(normyield)
        yield_buttons_layout.addWidget(self.standard_button)

        self.lowyield_button = QRadioButton("ALLE Karten (high-yield, normal UND low-yield)") # fmt: skip
        self.lowyield_button.setChecked(lowyield)
        yield_buttons_layout.addWidget(self.lowyield_button)

        # Explicitly group yield buttons
        self.yield_button_group = QButtonGroup(self)
        self.yield_button_group.addButton(self.highyield_stark_button)
        self.yield_button_group.addButton(self.highyield_all_button)
        self.yield_button_group.addButton(self.standard_button)
        self.yield_button_group.addButton(self.lowyield_button)

        yield_group_box.setLayout(yield_buttons_layout)
        settings_layout.addWidget(yield_group_box)

        # AUTOCREATE OPTIONS LAYOUT
        settings_layout.addSpacing(10)
        autocreate_group_box = QGroupBox()
        autocreate_options_layout = QVBoxLayout()
        autocreate_options_layout.setContentsMargins(5, 5, 5, 5)

        # AUTOCREATE DUE LERNTAG DECK
        due_layout = QHBoxLayout()
        self.autocreate_due_button = QRadioButton()
        self.autocreate_due_button.setChecked(autocreate_due)
        due_tooltip = (
            "Erstellt einen Auswahlstapel (<code>!FÄLLIGE KARTEN VERGANGENER "
            "LERNTAGE</code>) mit allen fälligen Karten aus vergangenen "
            "Lerntagen."
        )
        due_label = QLabel("Ich will die relevanten Lernplan‑Karten im Anki‑Algorithmus während des Lernplanes regelmäßig wiederholen. (Standard)") # fmt: skip
        due_label.setWordWrap(True)
        due_layout.addWidget(self.autocreate_due_button, 0)
        due_layout.insertWidget(1, self._info_icon_label(due_tooltip))
        due_layout.addWidget(due_label, 1)
        autocreate_options_layout.addLayout(due_layout)

        # AUTOCREATE PREVIOUS LERNTAG DECK
        previous_layout = QHBoxLayout()
        self.autocreate_previous_button = QRadioButton()
        self.autocreate_previous_button.setChecked(autocreate_previous)
        previous_tooltip = (
            "Erstellt die Auswahlstapel <code>!LERNTAG&nbsp;XX</code> jeden "
            "Tag neu, sammelt dabei alle (nicht nur fällige) Karten ein.<br>"
            "Die lange Liste an Lerntag-Stapeln ist dann unter "
            "<code>!VORHERIGE&nbsp;LERNTAGE</code> zu finden."
        )
        previous_label = QLabel("Ich will einzelne Lerntage später nochmal spezifisch wiederholen.") # fmt: skip
        previous_label.setWordWrap(True)
        previous_layout.addWidget(self.autocreate_previous_button, 0)
        previous_layout.insertWidget(1, self._info_icon_label(previous_tooltip))
        previous_layout.addWidget(previous_label, 1)
        autocreate_options_layout.addLayout(previous_layout)

        # AUTOCREATE NO PREVIOUS LERNTAG DECKS
        no_previous_layout = QHBoxLayout()
        self.autocreate_no_previous_button = QRadioButton()
        self.autocreate_no_previous_button.setChecked(autocreate_no_previous)
        noprev_tooltip = (
            "Nur <code>!LERNTAG&nbsp;XX</code> wird kreiert, alle gelernten "
            "Karten fallen in die ganz normale Rotation zurück.<br>Macht "
            "eigentlich nur Sinn, wenn du schon seit dem 5. Semester mit "
            "Ankizin lernst und im Lernplan nur auffrischst."
        )
        no_previous_label = QLabel("Ich will nur die relevanten Lernplan‑Karten ausgewählt haben.") # fmt: skip
        no_previous_label.setWordWrap(True)
        no_previous_layout.addWidget(self.autocreate_no_previous_button, 0)
        no_previous_layout.insertWidget(1, self._info_icon_label(noprev_tooltip)) # fmt: skip
        no_previous_layout.addWidget(no_previous_label, 1)
        autocreate_options_layout.addLayout(no_previous_layout)

        # Explicitly group autocreate buttons
        self.autocreate_button_group = QButtonGroup(self)
        self.autocreate_button_group.addButton(self.autocreate_due_button)
        self.autocreate_button_group.addButton(self.autocreate_previous_button)
        self.autocreate_button_group.addButton(self.autocreate_no_previous_button) # fmt: skip

        autocreate_group_box.setLayout(autocreate_options_layout)
        settings_layout.addWidget(autocreate_group_box)

        # Confirm button
        confirm_btn = QPushButton("Speichern und loslernen!")
        confirm_btn.setFixedWidth(200)
        settings_layout.addWidget(confirm_btn, alignment=Qt.AlignmentFlag.AlignLeft) # fmt: skip
        confirm_btn.clicked.connect(self.create_lerntag_deck_wrapper)

        self.settings_frame.setLayout(settings_layout)
        right_layout.addWidget(self.settings_frame)
        main_layout.addLayout(right_layout)

        self.setWindowIcon(QIcon("icons:ankizin.png"))

    def toggle_settings(self, checked):
        self.settings_frame.setVisible(checked)
        self.updateGeometry()
        self.resize(0, 0)
        self.adjustSize()

    def closeEvent(self, event):
        self.save_config()
        event.ignore()
        self.reject()

    def get_lerntag_list(self):
        col = mw.col
        # match only main Lerntag tags
        lerntag_pattern = re.compile(
            r"#Ankizin_v(?:\d+|Ankihub)(?:::[^:]+)*::M2_Lerntag_(\d{3})_(.+)$"
        )
        lerntag_tags = [
            tag for tag in col.tags.all() if lerntag_pattern.match(tag)
        ]

        unique_lerntag = {}
        for tag in lerntag_tags:
            match = lerntag_pattern.match(tag)
            if match:
                number, topic = match.group(1), match.group(2)
                if number not in unique_lerntag:
                    unique_lerntag[number] = topic

        lerntag_list = sorted(unique_lerntag.items(), key=lambda x: int(x[0]))
        return lerntag_list

    def save_config(self):
        # Get the config
        conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
        if conf is None:
            conf = {}
        if "lernplan" not in conf:
            conf["lernplan"] = {}
        lernplan_conf = conf["lernplan"]

        lerntag = self.lerntag_combo.currentData().zfill(3)
        highyield_stark = self.highyield_stark_button.isChecked()
        highyield_leicht = self.highyield_all_button.isChecked()  # If "all" is selected, include leicht
        lowyield = self.lowyield_button.isChecked()
        top100 = self.top100_button.isChecked()
        autocreate_due = self.autocreate_due_button.isChecked()
        autocreate_previous = self.autocreate_previous_button.isChecked()
        autocreate_no_previous = self.autocreate_no_previous_button.isChecked()

        # Save the config
        lernplan_conf["lerntag"] = lerntag
        lernplan_conf["highyield_stark"] = highyield_stark
        lernplan_conf["highyield_leicht"] = highyield_leicht
        # Keep old highyield for backwards compatibility
        lernplan_conf["highyield"] = highyield_stark or highyield_leicht
        lernplan_conf["normyield"] = self.standard_button.isChecked()
        lernplan_conf["lowyield"] = lowyield
        lernplan_conf["top100"] = top100
        lernplan_conf["autocreate"] = self.autocreate_button.isChecked()
        lernplan_conf["autocreate_due"] = autocreate_due
        lernplan_conf["autocreate_previous"] = autocreate_previous
        lernplan_conf["autocreate_no_previous"] = autocreate_no_previous
        lernplan_conf["wochentage"] = [
            button.isChecked() for button in self.weekday_buttons
        ]
        lernplan_conf["last_updated"] = (
            datetime.datetime.today().date().isoformat()
        )
        lernplan_conf["lernplan_started_on"] = (
            datetime.datetime.today().weekday()
        )
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
        return (
            lerntag,
            highyield_stark,
            highyield_leicht,
            lowyield,
            top100,
            autocreate_previous,
            autocreate_due,
        )

    @staticmethod
    def on_success(changes: OpChanges):
        pass

    def create_lerntag_deck_wrapper(self):
        # save config + get values
        (
            lerntag,
            highyield_stark,
            highyield_leicht,
            lowyield,
            top100,
            _previous,
            _due,
        ) = self.save_config()

        # Remove previous filtered decks
        remove_previous_lerntag_decks()

        # Create the filtered deck
        create_lerntag_deck(
            lerntag,
            highyield_stark,
            highyield_leicht,
            lowyield,
            top100,
        )

        # Create the previous due deck if necessary
        if _due:
            create_lerntag_due_deck(
                lerntag,
                highyield_stark,
                highyield_leicht,
                lowyield,
                top100,
            )

        # Create the previous filtered decks if necessary
        if _previous:
            CollectionOp(
                parent=aqt.mw,
                op=lambda _: create_previous_lerntag_decks(
                    lerntag,
                    highyield_stark,
                    highyield_leicht,
                    lowyield,
                    top100,
                ),
            ).success(LernplanManagerDialog.on_success).run_in_background()

        self.accept()
        mw.reset()

    def _info_icon_label(self, tooltip: str) -> QLabel:
        dummy = QCheckBox()
        icon = dummy.style().standardIcon(
            QStyle.StandardPixmap.SP_MessageBoxInformation
        )
        result = QLabel("")
        pixmap = icon.pixmap(dummy.iconSize())
        result.setPixmap(pixmap)
        result.setToolTip(tooltip)
        result.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        return result


class LerntagDeckCreatorDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Lerntag-Auswahlstapel erstellen")

        main_layout = QHBoxLayout(self)
        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        # Get the config
        conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
        if conf is None:
            lerntag = 0  # 0-indexed
            highyield_stark, highyield_leicht, normyield, lowyield = (
                False,
                False,
                True,
                False,
            )
            top100 = False
        else:
            lernplan_conf = conf.get("man_lernplan", {})
            # config contains e.g. "035" but we want 0-indexed
            lerntag = int(lernplan_conf.get("lerntag", "001")) - 1
            # Handle both old "highyield" and new separate options
            highyield_stark = lernplan_conf.get("highyield_stark", False)
            highyield_leicht = lernplan_conf.get("highyield_leicht", False)
            # For backward compatibility with old configs
            if (
                lernplan_conf.get("highyield", False)
                and not highyield_stark
                and not highyield_leicht
            ):
                highyield_stark = True
                highyield_leicht = True
            normyield = lernplan_conf.get("normyield", True)
            lowyield = lernplan_conf.get("lowyield", False)
            top100 = lernplan_conf.get("top100", False)

        # Logo
        logo_label = QLabel()
        logo_pixmap = QPixmap("icons:ankizin.png")
        logo_label.setPixmap(
            logo_pixmap.scaled(
                100,
                100,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        main_layout.addWidget(logo_label)

        # Right side layout
        right_layout = QVBoxLayout()

        # EXPLANATION
        right_layout.addWidget(
            QLabel(
                "Erstelle einen spezifischen Lerntag-Auswahlstapel <b>unabhängig</b> vom<br>automatischen Lernplan-Manager."
            )
        )
        right_layout.addSpacing(20)

        # LERNTAG SELECTION MENU
        right_layout.addWidget(QLabel("<b>Lerntag:</b>"))
        self.lerntag_combo = QComboBox()
        for number, topic in self.get_lerntag_list():
            display_text = f"{number} - {topic.replace('_', ' ')}"
            self.lerntag_combo.addItem(display_text, number)
        self.lerntag_combo.setCurrentIndex(lerntag)
        right_layout.addWidget(self.lerntag_combo)

        self.top100_button = QCheckBox("nur TOP-100 Themen")
        self.top100_button.setChecked(top100)
        self.top100_button.setToolTip(
            "Beschränkt die Auswahl auf die wichtigsten 100 Themen aus AMBOSS."
        )
        right_layout.addWidget(self.top100_button)

        self.highyield_stark_button = QRadioButton(
            "nur HIGH-YIELD stark gelb"
        )
        self.highyield_stark_button.setChecked(
            highyield_stark and not highyield_leicht
        )
        right_layout.addWidget(self.highyield_stark_button)

        self.highyield_all_button = QRadioButton(
            "alle HIGH-YIELD Karten (stark + leicht gelb)"
        )
        self.highyield_all_button.setChecked(
            highyield_stark and highyield_leicht
        )
        right_layout.addWidget(self.highyield_all_button)

        self.standard_button = QRadioButton("STANDARD Karten (high-yield und normal)") # fmt: skip
        self.standard_button.setChecked(normyield)
        right_layout.addWidget(self.standard_button)

        self.lowyield_button = QRadioButton("ALLE Karten (high-yield, normal UND low-yield)") # fmt: skip
        self.lowyield_button.setChecked(lowyield)
        right_layout.addWidget(self.lowyield_button)

        # Explicitly group yield buttons
        self.yield_button_group = QButtonGroup(self)
        self.yield_button_group.addButton(self.highyield_stark_button)
        self.yield_button_group.addButton(self.highyield_all_button)
        self.yield_button_group.addButton(self.standard_button)
        self.yield_button_group.addButton(self.lowyield_button)

        # Confirm button
        confirm_btn = QPushButton("Stapel erstellen!")
        confirm_btn.setFixedWidth(150)
        right_layout.addWidget(confirm_btn, alignment=Qt.AlignmentFlag.AlignLeft) # fmt: skip
        confirm_btn.clicked.connect(self.create_lerntag_deck_wrapper)

        main_layout.addLayout(right_layout)

        self.setWindowIcon(QIcon("icons:ankizin.png"))

    def closeEvent(self, event):
        event.ignore()
        self.reject()

    def get_lerntag_list(self):
        col = mw.col
        # match only main Lerntag tags
        lerntag_pattern = re.compile(
            r"#Ankizin_v(?:\d+|Ankihub)(?:::[^:]+)*::M2_Lerntag_(\d{3})_(.+)$"
        )
        lerntag_tags = [
            tag for tag in col.tags.all() if lerntag_pattern.match(tag)
        ]

        unique_lerntag = {}
        for tag in lerntag_tags:
            match = lerntag_pattern.match(tag)
            if match:
                number, topic = match.group(1), match.group(2)
                if number not in unique_lerntag:
                    unique_lerntag[number] = topic

        lerntag_list = sorted(unique_lerntag.items(), key=lambda x: int(x[0]))
        return lerntag_list

    def save_config(self):
        # Get the config
        conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
        if conf is None:
            conf = {}
        if "man_lernplan" not in conf:
            conf["man_lernplan"] = {}
        lernplan_conf = conf["man_lernplan"]

        lerntag = self.lerntag_combo.currentData().zfill(3)
        highyield_stark = self.highyield_stark_button.isChecked()
        highyield_leicht = self.highyield_all_button.isChecked()  # If "all" is selected, include leicht
        lowyield = self.lowyield_button.isChecked()
        top100 = self.top100_button.isChecked()

        # Save the config
        lernplan_conf["lerntag"] = lerntag
        lernplan_conf["highyield_stark"] = highyield_stark
        lernplan_conf["highyield_leicht"] = highyield_leicht
        # Keep old highyield for backwards compatibility
        lernplan_conf["highyield"] = highyield_stark or highyield_leicht
        lernplan_conf["normyield"] = self.standard_button.isChecked()
        lernplan_conf["lowyield"] = lowyield
        lernplan_conf["top100"] = top100
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
        return (
            lerntag,
            highyield_stark,
            highyield_leicht,
            lowyield,
            top100,
        )

    def create_lerntag_deck_wrapper(self):
        # save config + get values
        (
            lerntag,
            highyield_stark,
            highyield_leicht,
            lowyield,
            top100,
        ) = self.save_config()

        # Create the filtered deck
        create_lerntag_deck(
            lerntag,
            highyield_stark,
            highyield_leicht,
            lowyield,
            top100,
            deck_name_prefix="Lerntag ",
        )
        self.accept()
        mw.reset()


def remove_previous_lerntag_decks():
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    # match only main Lerntage
    for deck in mw.col.decks.all_names_and_ids():
        if (
            deck.name.startswith("!LERNTAG ")
            or deck.name.startswith("!FÄLLIGE KARTEN VERGANGENER LERNTAGE")
        ) and col.decks.is_filtered(deck.id):
            remove_filtered_deck(deck.id)


def create_previous_lerntag_decks(
    lerntag,
    highyield_stark,
    highyield_leicht,
    lowyield,
    top100=False,
):
    for i in range(int(lerntag) - 1, 0, -1):
        create_lerntag_deck(
            str(i).zfill(3),
            highyield_stark,
            highyield_leicht,
            lowyield,
            top100,
            sup_deck_name="!VORHERIGE LERNTAGE",
            silent=True,
        )
    return OpChanges()


def create_lerntag_due_deck(
    lerntag,
    highyield_stark,
    highyield_leicht,
    lowyield,
    top100=False,
    silent=False,
):
    # Due cards only make sense if there is a past Lerntag
    if int(lerntag) < 2:
        return

    col = mw.col
    if col is None:
        raise Exception("collection not available")

    lerntage = "|".join([str(i).zfill(3) for i in range(1, int(lerntag))])
    tag_pattern = f"#Ankizin_(.*?)::#M2_M3_Klinik::#AMBOSS::M2-100-Tage-Lernplan::M2_Lerntag_({lerntage})"
    search = col.build_search_string(f'is:due "tag:re:{tag_pattern}"')
    deck_name = f"!FÄLLIGE KARTEN VERGANGENER LERNTAGE"

    # Filter for TOP-100 themes first (if enabled)
    if top100:
        top100_tag = "#Ankizin_*::#M2_M3_Klinik::#AMBOSS::M2-TOP100-Themen"
        search += f' "tag:{top100_tag}"'

    # Select only high-yield cards
    if highyield_stark:
        high_yield_tags = [
            "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)::stark_gelb_M2",
            "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz::01-stark_gelb_M2",
        ]

        if highyield_leicht:  # "all" button selected
            high_yield_tags.extend(
                [
                    "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)::leicht_gelb_M2",
                    "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz::02-leicht_gelb_M2",
                ]
            )

        high_yield_search = " OR ".join(
            [f'"tag:{tag}"' for tag in high_yield_tags]
        )
        search += f" ({high_yield_search})"
    # Exclude low-yield cards
    elif not lowyield:
        low_yield_tags = [
            "#Ankizin_vAnkihub::!MARKIERE_DIESE_KARTEN::M2_low_yield",
            "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz::04-low_yield_(verzichtbar)_M2",
        ]
        low_yield_search = " OR ".join(
            [f'"tag:{tag}"' for tag in low_yield_tags]
        )
        search += f" -({low_yield_search})"

    create_filtered_deck(deck_name, search, duedeck=True, silent=silent)


def create_lerntag_deck(
    lerntag,
    highyield_stark,
    highyield_leicht,
    lowyield,
    top100=False,
    deck_name_prefix: str = None,
    sup_deck_name: str = None,
    silent=False,
):
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    tag_pattern = f"#Ankizin_*::#M2_M3_Klinik::#AMBOSS::M2-100-Tage-Lernplan::M2_Lerntag_{lerntag}_*"
    search = col.build_search_string(f'"tag:{tag_pattern}"')
    deck_name = deck_name_prefix if deck_name_prefix else "!LERNTAG "
    deck_name += f"{lerntag}"

    # Filter for TOP-100 themes first (if enabled)
    if top100:
        top100_tag = "#Ankizin_*::#M2_M3_Klinik::#AMBOSS::M2-TOP100-Themen"
        search += f' "tag:{top100_tag}"'
        deck_name += " - TOP-100"

    # Select only high-yield cards
    if highyield_stark:
        high_yield_tags = [
            "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)::stark_gelb_M2",
            "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz::01-stark_gelb_M2",
        ]

        if highyield_leicht:  # "all" button selected
            high_yield_tags.extend(
                [
                    "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)::leicht_gelb_M2",
                    "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz::02-leicht_gelb_M2",
                ]
            )

        high_yield_search = " OR ".join(
            [f'"tag:{tag}"' for tag in high_yield_tags]
        )
        search += f" ({high_yield_search})"

        if highyield_leicht:
            deck_name += " - high-yield (alle)"
        elif highyield_stark:
            deck_name += " - high-yield (stark gelb)"
    # Exclude low-yield cards
    elif not lowyield:
        low_yield_tags = [
            "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_low_yield",
            "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz::04-low_yield_(verzichtbar)_M2",
        ]
        low_yield_search = " OR ".join(
            [f'"tag:{tag}"' for tag in low_yield_tags]
        )
        search += f" -({low_yield_search})"
    # Don't exclude low-yield cards
    else:
        deck_name += " - inkl. low-yield"

    if sup_deck_name:
        deck_name = f"{sup_deck_name}::{deck_name}"

    create_filtered_deck(deck_name, search, top100=top100, silent=silent)


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
