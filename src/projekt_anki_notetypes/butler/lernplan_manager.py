from aqt import mw
from aqt.qt import *
import re
import anki

from .utils import check_ankizin_installation


class LernplanManagerDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Lernplan Manager")

        main_layout = QHBoxLayout(self)

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
            display_text = f"{number} - {topic}"
            self.lerntag_combo.addItem(display_text, number)
        right_layout.addWidget(self.lerntag_combo)

        self.yield_checkbox = QCheckBox("Nur High yield Karten")
        right_layout.addWidget(self.yield_checkbox)

        self.exclude_lowyield = QCheckBox("Low Yield Karten ausschließen")
        right_layout.addWidget(self.exclude_lowyield)

        # Confirm button
        confirm_btn = QPushButton("Stapel erstellen!")
        confirm_btn.setFixedWidth(150)
        right_layout.addWidget(
            confirm_btn, alignment=Qt.AlignmentFlag.AlignLeft
        )
        confirm_btn.clicked.connect(self.create_filtered_deck)

        main_layout.addLayout(right_layout)

        self.setWindowIcon(QIcon("icons:ankizin.png"))

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

    def create_filtered_deck(self):
        col = mw.col
        if col is None:
            raise Exception("collection not available")
        lerntag = self.lerntag_combo.currentData().zfill(3)
        yield_checked = self.yield_checkbox.isChecked()
        no_lowyield = self.exclude_lowyield.isChecked()

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

        if yield_checked:
            high_yield_tag = f"#Ankizin_{latest_version}::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)"
            search += f' tag:"{high_yield_tag}"'
            deck_name = f"High yield - Lerntag {lerntag}"
        else:
            deck_name = f"Lerntag {lerntag}"

        if no_lowyield:
            low_yield_tag = f"#Ankizin_{latest_version}::!MARKIERE_DIESE_KARTEN::M2_low_yield"
            search += f' -tag:"{low_yield_tag}"'

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

        self.accept()


def open_lernplan_manager(self):
    # Check if Ankizin is installed
    if not check_ankizin_installation():
        return

    LernplanManagerDialog(mw).exec()
