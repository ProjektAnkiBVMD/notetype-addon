from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, askUser
import anki.hooks
import re
import webbrowser
import anki
from aqt.utils import showInfo
from aqt import mw


class FirstSetupConfigDialog(QDialog):
    def __init__(self, parent, helper):
        super().__init__(parent)
        self.helper = helper
        self.setWindowTitle("Ankizin Installations Konfiguration")

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

        # Explanatory text
        info_label = QLabel(
            "Neu bei Ankizin? Herzlich Willkommen! Aller Anfang ist schwer, und um dein Leben etwas leichter zu machen kannst du hier ein paar Einstellungen automatisch vornehmen lassen."
        )
        info_label.setWordWrap(True)
        right_layout.addWidget(info_label)

        # Checkboxes
        self.delete_cb = QCheckBox("Zum Löschen markierte Karten entfernen")
        self.delete_cb.setChecked(self.helper.delete_outdated_cards)
        right_layout.addWidget(self.delete_cb)

        self.suspend_all_cb = QCheckBox("Alle Karten aussetzen")
        self.suspend_all_cb.setChecked(self.helper.suspend_all_cards)
        right_layout.addWidget(self.suspend_all_cb)

        self.deck_cb = QCheckBox(
            "Empfohlene Einstellungen übernehmen (Sinnvoll, wenn du neu bei Anki bist)"
        )
        self.deck_cb.setChecked(self.helper.update_deck_config)
        right_layout.addWidget(self.deck_cb)

        # Confirm button
        confirm_btn = QPushButton("Loslegen!")
        confirm_btn.setFixedWidth(200)
        right_layout.addWidget(
            confirm_btn, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        confirm_btn.clicked.connect(self.confirm)

        main_layout.addLayout(right_layout)

        self.setWindowIcon(QIcon("icons:ankizin.png"))

    def confirm(self):
        self.helper.set_delete_outdated_cards(self.delete_cb.isChecked())
        self.helper.set_update_deck_config(self.deck_cb.isChecked())
        self.helper.set_suspend_all_cards(self.suspend_all_cb.isChecked())
        self.accept()

    def closeEvent(self, event):
        event.ignore()
        self.reject()


class UpdateConfigDialog(QDialog):
    def __init__(self, parent, helper):
        super().__init__(parent)
        self.helper = helper
        self.setWindowTitle("Ankizin Update Konfiguration")

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

        # Explanatory text
        info_label = QLabel(
            "Frisch eine neue Version von Ankizin heruntergeladen? Hier kannst du einige Aufräumarbeiten automatisch erledigen lassen."
        )
        info_label.setWordWrap(True)
        right_layout.addWidget(info_label)

        # Checkboxes
        self.delete_cb = QCheckBox("Zum Löschen markierte Karten entfernen")
        self.delete_cb.setChecked(self.helper.delete_outdated_cards)
        right_layout.addWidget(self.delete_cb)

        self.suspend_new_cb = QCheckBox("Neuen Karten aussetzen")
        self.suspend_new_cb.setChecked(self.helper.suspend_new_cards)
        right_layout.addWidget(self.suspend_new_cb)

        # Confirm button
        confirm_btn = QPushButton("Loslegen!")
        confirm_btn.setFixedWidth(150)
        right_layout.addWidget(
            confirm_btn, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        confirm_btn.clicked.connect(self.confirm)

        main_layout.addLayout(right_layout)

        self.setWindowIcon(QIcon("icons:ankizin.png"))

    def confirm(self):
        self.helper.set_delete_outdated_cards(self.delete_cb.isChecked())
        self.helper.set_suspend_new_cards(self.suspend_new_cb.isChecked())
        self.accept()

    def closeEvent(self, event):
        event.ignore()
        self.reject()
