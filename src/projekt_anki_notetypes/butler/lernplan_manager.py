import datetime
import re
from pathlib import Path

import anki
from aqt import mw
from aqt.qt import *

from .utils import check_ankizin_installation

ADDON_DIR_NAME = str(Path(__file__).parent.parent.name)


class LernplanManagerDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Lernplan-Manager")

        main_layout = QHBoxLayout(self)

        # Get the config
        conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
        if conf is None:
            lerntag = 0  # 0-indexed
            highyield, normyield, lowyield = False, True, False
        else:
            lernplan_conf = conf.get("lernplan", {})
            # config contains e.g. "035" but we want 0-indexed
            lerntag = int(lernplan_conf.get("lerntag", 1)) - 1
            highyield = lernplan_conf.get("highyield", False)
            normyield = lernplan_conf.get("normyield", True)
            lowyield = lernplan_conf.get("lowyield", False)
            autocreate = lernplan_conf.get("autocreate", False)
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
            "Lerntag-Deck jeden Tag automatisch erstellen"
        )
        self.autocreate_button.setChecked(autocreate)
        right_layout.addWidget(self.autocreate_button)

        # WOCHENTAGE AUSWÄHLEN
        right_layout.addSpacing(10)
        weekdays = QGroupBox("Wochentage für den Lernplan:")
        weekdays_layout = QHBoxLayout()
        self.weekday_buttons = []
        for weekday, check in zip(["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"], wochentage):
            button = QCheckBox(weekday)
            button.setChecked(check)
            self.weekday_buttons.append(button)
            weekdays_layout.addWidget(button)
        weekdays.setLayout(weekdays_layout)
        right_layout.addWidget(weekdays)

        # Confirm button
        confirm_btn = QPushButton("Stapel erstellen!")
        confirm_btn.setFixedWidth(150)
        right_layout.addWidget(
            confirm_btn, alignment=Qt.AlignmentFlag.AlignLeft
        )
        confirm_btn.clicked.connect(self.create_filtered_deck_wrapper)

        main_layout.addLayout(right_layout)

        self.setWindowIcon(QIcon("icons:ankizin.png"))
        
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

        # Save the config
        lernplan_conf["lerntag"] = lerntag
        lernplan_conf["highyield"] = highyield
        lernplan_conf["normyield"] = self.standard_button.isChecked()
        lernplan_conf["lowyield"] = lowyield
        lernplan_conf["autocreate"] = self.autocreate_button.isChecked()
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
        return lerntag, highyield, lowyield
    
    def create_filtered_deck_wrapper(self):
        # save config + get values
        lerntag, highyield, lowyield = self.save_config()

        # Create the filtered deck
        create_filtered_deck(lerntag, highyield, lowyield)
        self.accept()


def create_filtered_deck(lerntag, highyield, lowyield):
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    # Determine the latest Ankizin_v version dynamically
    pattern = re.compile(r"#Ankizin_v(\d+)::")
    versions = []
    for tag in col.tags.all():
        match = pattern.match(tag)
        if match:
            versions.append(int(match.group(1)))
    if versions:
        latest_version = f"v{max(versions)}"
    else:
        latest_version = "vAnkihub"

    tag_pattern = f"#Ankizin_{latest_version}::#M2_M3_Klinik::#AMBOSS::M2-100-Tage-Lernplan::M2_Lerntag_{lerntag}_*"
    search = col.build_search_string(f'tag:"{tag_pattern}"')

    if highyield:
        high_yield_tag = f"#Ankizin_{latest_version}::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)"
        search += f' tag:"{high_yield_tag}"'
        deck_name = f"Lerntag {lerntag} - nur high-yield"
    elif lowyield:
        deck_name = f"Lerntag {lerntag} - inkl. low-yield"
    else:
        low_yield_tag = (
            f"#Ankizin_{latest_version}::!MARKIERE_DIESE_KARTEN::M2_low_yield"
        )
        search += f' -tag:"{low_yield_tag}"'
        deck_name = f"Lerntag {lerntag}"

    # Unsuspend all cards that are not yet unsuspended, sonst nicht im dynamic deck
    cidsToUnsuspend = col.find_cards(search)
    col.sched.unsuspend_cards(cidsToUnsuspend)

    print(search)
    mw.progress.start()
    did = col.decks.new_filtered(deck_name)
    deck = col.decks.get(did)

    print(f"Found cards: {len(col.find_cards(search))}")

    deck["terms"] = [[search, 999, 2]]

    col.decks.save(deck)

    # Force rebuild
    col.sched.rebuild_filtered_deck(did)
    mw.progress.finish()
    mw.reset()

    card_count = len(col.decks.cids(did))
    print(f"Created deck with {card_count} cards")


def open_lernplan_manager(self):
    # Check if Ankizin is installed
    if not check_ankizin_installation():
        return

    dialog = LernplanManagerDialog(mw)
    dialog.setFixedSize(dialog.sizeHint())
    dialog.exec()
