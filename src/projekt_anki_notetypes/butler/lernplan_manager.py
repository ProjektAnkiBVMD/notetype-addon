import datetime
import re
from pathlib import Path

import anki
from aqt import mw
from aqt.qt import *
from anki.decks import FilteredDeckConfig
from anki.scheduler import FilteredDeckForUpdate
from anki.errors import FilteredDeckError
from aqt.utils import showWarning

from .utils import (
    check_ankizin_installation,
    create_filtered_deck,
    remove_filtered_deck,
)

ADDON_DIR_NAME = str(Path(__file__).parent.parent.name)


class LernplanManagerDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Lernplan-Manager")

        main_layout = QHBoxLayout(self)
        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        # Get the config
        conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
        if conf is None:
            lerntag = 0  # 0-indexed
            highyield, normyield, lowyield = False, True, False
        else:
            lernplan_conf = conf.get("lernplan", {})
            # config contains e.g. "035" but we want 0-indexed
            lerntag = int(lernplan_conf.get("lerntag", "001")) - 1
            highyield = lernplan_conf.get("highyield", False)
            normyield = lernplan_conf.get("normyield", True)
            lowyield = lernplan_conf.get("lowyield", False)
            autocreate = lernplan_conf.get("autocreate", False)
            autocreate_previous = lernplan_conf.get("autocreate_previous", True)
            wochentage = lernplan_conf.get("wochentage", [False] * 7)

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

        right_layout.addWidget(QLabel("Lerntag:"))
        self.lerntag_combo = QComboBox()
        for number, topic in self.get_lerntag_list():
            display_text = f"{number} - {topic.replace('_', ' ')}"
            self.lerntag_combo.addItem(display_text, number)
        self.lerntag_combo.setCurrentIndex(lerntag)
        right_layout.addWidget(self.lerntag_combo)

        self.highyield_button = QRadioButton("nur HIGH-YIELD Karten")
        self.highyield_button.setChecked(highyield)
        right_layout.addWidget(self.highyield_button)

        self.standard_button = QRadioButton(
            "STANDARD Karten (high-yield und normal)"
        )
        self.standard_button.setChecked(normyield)
        right_layout.addWidget(self.standard_button)

        self.lowyield_button = QRadioButton(
            "ALLE Karten (high-yield, normal UND low-yield)"
        )
        self.lowyield_button.setChecked(lowyield)
        right_layout.addWidget(self.lowyield_button)

        # AUTOCREATE LERNTAG DECK
        right_layout.addSpacing(30)
        self.autocreate_button = QCheckBox(
            "Lerntag-Stapel jeden Tag automatisch erstellen"
        )
        self.autocreate_button.setChecked(autocreate)
        self.autocreate_button.toggled.connect(
            self.toggle_weekdays
        )  # Changed signal
        right_layout.addWidget(self.autocreate_button)

        # AUTOCREATE PREVIOUS LERNTAG DECK
        self.autocreate_previous_button = QCheckBox(
            "vorherige Lerntag-Stapel behalten (unter !VORHERIGE_LERNTAGE)"
        )
        self.autocreate_previous_button.setChecked(autocreate_previous)
        right_layout.addWidget(self.autocreate_previous_button)

        # WOCHENTAGE AUSWÄHLEN
        right_layout.addSpacing(10)
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
        self.weekdays.setVisible(autocreate)
        right_layout.addWidget(self.weekdays)

        # Confirm button
        confirm_btn = QPushButton("Stapel erstellen!")
        confirm_btn.setFixedWidth(150)
        right_layout.addWidget(
            confirm_btn, alignment=Qt.AlignmentFlag.AlignLeft
        )
        confirm_btn.clicked.connect(self.create_lerntag_deck_wrapper)

        main_layout.addLayout(right_layout)

        self.setWindowIcon(QIcon("icons:ankizin.png"))

    def toggle_weekdays(self, checked):
        self.weekdays.setVisible(checked)
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
        highyield = self.highyield_button.isChecked()
        lowyield = self.lowyield_button.isChecked()
        autocreate_previous = self.autocreate_previous_button.isChecked()

        # Save the config
        lernplan_conf["lerntag"] = lerntag
        lernplan_conf["highyield"] = highyield
        lernplan_conf["normyield"] = self.standard_button.isChecked()
        lernplan_conf["lowyield"] = lowyield
        lernplan_conf["autocreate"] = self.autocreate_button.isChecked()
        lernplan_conf["autocreate_previous"] = autocreate_previous
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
        return lerntag, highyield, lowyield, autocreate_previous

    def create_lerntag_deck_wrapper(self):
        # save config + get values
        lerntag, highyield, lowyield, autocreate_previous = self.save_config()

        # Remove previous filtered decks
        remove_previous_lerntag_decks()

        # Create the filtered deck
        create_lerntag_deck(lerntag, highyield, lowyield)

        # Create the previous filtered decks if necessary
        if autocreate_previous:
            create_previous_lerntag_decks(lerntag, highyield, lowyield)

        self.accept()


def remove_previous_lerntag_decks():
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    # match only main Lerntage
    for deck in mw.col.decks.all_names_and_ids():
        if deck.name.startswith("!LERNTAG ") and col.decks.is_filtered(deck.id):
            remove_filtered_deck(deck.id)


def create_previous_lerntag_decks(lerntag, highyield, lowyield):
    for i in range(int(lerntag) - 1, 0, -1):
        create_lerntag_deck(
            str(i).zfill(3), highyield, lowyield, "!VORHERIGE_LERNTAGE"
        )


def create_lerntag_deck(
    lerntag, highyield, lowyield, deck_name_prefix: str = None
):
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    tag_pattern = f"#Ankizin_*::#M2_M3_Klinik::#AMBOSS::M2-100-Tage-Lernplan::M2_Lerntag_{lerntag}_*"
    search = col.build_search_string(f'tag:"{tag_pattern}"')
    deck_name = "Lerntag " if deck_name_prefix else "!LERNTAG "

    # Select only high-yield cards
    if highyield:
        high_yield_tag = (
            f"#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)"
        )
        search += f' tag:"{high_yield_tag}"'
        deck_name += f"{lerntag} - high-yield"
    # Exclude low-yield cards
    elif not lowyield:
        low_yield_tag = f"#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_low_yield"
        search += f' -tag:"{low_yield_tag}"'
        deck_name += f"{lerntag}"
    # Don't exclude low-yield cards
    else:
        deck_name += f"{lerntag} - inkl. low-yield"

    if deck_name_prefix:
        deck_name = f"{deck_name_prefix}::{deck_name}"

    create_filtered_deck(deck_name, search)


def open_lernplan_manager(self):
    # Check if Ankizin is installed
    if not check_ankizin_installation():
        return

    dialog = LernplanManagerDialog(mw)
    # dialog.setFixedSize(dialog.sizeHint())
    dialog.exec()
