from aqt.qt import *
from aqt.utils import disable_help_button


class _HelperDialog(QDialog):
    """Logo, explanation, checkboxes and one confirm button; subclasses add the checkboxes."""

    title = ""
    info = ""

    def __init__(self, parent, helper):
        super().__init__(parent)
        disable_help_button(self)
        self.helper = helper
        self.setWindowTitle(self.title)

        main_layout = QHBoxLayout(self)
        logo_label = QLabel()
        logo_label.setPixmap(
            QPixmap("icons:ankizin.png").scaled(
                100,
                100,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        main_layout.addWidget(logo_label)

        right_layout = QVBoxLayout()
        info_label = QLabel(self.info)
        info_label.setWordWrap(True)
        right_layout.addWidget(info_label)
        self.delete_cb = self._checkbox(
            right_layout, "Zum Löschen markierte Karten entfernen", helper.delete_outdated_cards
        )
        self._add_checkboxes(right_layout)

        buttons = QDialogButtonBox()
        confirm_btn = buttons.addButton("Loslegen!", QDialogButtonBox.ButtonRole.AcceptRole)
        confirm_btn.setDefault(True)
        confirm_btn.clicked.connect(self.confirm)
        right_layout.addWidget(buttons)

        main_layout.addLayout(right_layout)
        self.setWindowIcon(QIcon("icons:ankizin.png"))

    @staticmethod
    def _checkbox(layout: QVBoxLayout, text: str, checked: bool) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.setChecked(checked)
        layout.addWidget(checkbox)
        return checkbox

    def _add_checkboxes(self, layout: QVBoxLayout) -> None:
        raise NotImplementedError

    def confirm(self):
        self.helper.set_delete_outdated_cards(self.delete_cb.isChecked())
        self._save()
        self.accept()

    def _save(self) -> None:
        raise NotImplementedError

    def closeEvent(self, event):
        event.ignore()
        self.reject()


class FirstSetupConfigDialog(_HelperDialog):
    title = "Ankizin Installations-Konfiguration"
    info = (
        "Neu bei Ankizin? Herzlich Willkommen!<br>"
        "Aller Anfang ist schwer. Um dein Leben etwas leichter zu machen, kannst du hier ein paar Einstellungen automatisch vornehmen lassen."
    )

    def _add_checkboxes(self, layout):
        self.suspend_all_cb = self._checkbox(layout, "Alle Karten aussetzen", self.helper.suspend_all_cards)
        self.deck_cb = self._checkbox(
            layout,
            "Empfohlene Einstellungen übernehmen (sinnvoll, wenn du neu bei Anki bist!)",
            self.helper.update_deck_config,
        )

    def _save(self):
        self.helper.set_update_deck_config(self.deck_cb.isChecked())
        self.helper.set_suspend_all_cards(self.suspend_all_cb.isChecked())


class UpdateConfigDialog(_HelperDialog):
    title = "Ankizin Update-Konfiguration"
    info = (
        "Frisch eine neue Version von Ankizin heruntergeladen?<br>"
        "Hier kannst du einige Aufräumarbeiten automatisch erledigen lassen."
    )

    def _add_checkboxes(self, layout):
        self.suspend_new_cb = self._checkbox(layout, "Neue Karten aussetzen", self.helper.suspend_new_cards)

    def _save(self):
        self.helper.set_suspend_new_cards(self.suspend_new_cb.isChecked())
