from pathlib import Path
import aqt
from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, askUser
import anki
import anki.hooks
import re
import webbrowser
from aqt.utils import showInfo
import aqt.forms.preferences

from .ankizin_helper import AnkizinHelper
from .lernplan_manager import open_lernplan_manager, open_lerntag_deck_creator

from ..gui.projekt_anki_menu import get_ankizin_menu

ankizin_helper = None


def init_ankizin_helper(menu):
    global ankizin_helper
    ankizin_helper = AnkizinHelper()

    # Add menu item
    first_setup = QAction("Ankizin erstmalig installiert?", mw)
    first_setup.triggered.connect(ankizin_helper.run_first_time_setup)

    update_setup = QAction("Ankizin-Update installiert?", mw)
    update_setup.triggered.connect(ankizin_helper.run_ankizin_update_setup)

    menu.addAction(first_setup)
    menu.addAction(update_setup)

    print("Ankizin helper initialized")


def add_lernplan_manager(menu):
    action = QAction("Lernplan-Manager (automatisch)", mw)
    action.triggered.connect(open_lernplan_manager)
    menu.addAction(action)


def add_lerntag_deck_creator(menu):
    action = QAction("Lerntag-Auswahlstapel erstellen (manuell)", mw)
    action.triggered.connect(open_lerntag_deck_creator)
    menu.addAction(action)


def get_rebuild_config():
    conf = mw.addonManager.getConfig(str(Path(__file__).parent.parent.name))

    if conf is None:
        conf = {}

    # Ensure the key exists, setting the default value if it doesn't.
    conf.setdefault("autoRebuildDecksOnStartup", True)

    return conf


def on_auto_rebuild_checkbox_changed(checked: bool):
    """Called when the user clicks the checkbox in Preferences."""
    conf = get_rebuild_config()
    key = "autoRebuildDecksOnStartup"
    conf[key] = checked

    mw.addonManager.writeConfig(str(Path(__file__).parent.parent.name), conf)
    print("Auto rebuild setting changed:", conf[key])


def setup_rebuild_settings_toggle():
    # monkey patch the setupUi method of the Preferences dialog
    original_form_setupUi = aqt.forms.preferences.Ui_Preferences.setupUi

    def preferences_ui_with_ankizin(self, PreferencesDialog):
        # og call
        original_form_setupUi(self, PreferencesDialog)

        try:
            # Find the target widget (the 'Render LaTeX' checkbox) in the review tab we use as reference
            target_widget = self.render_latex
            if not isinstance(target_widget, QCheckBox):
                raise AttributeError("Target widget 'render_latex' is not a QCheckBox.") # fmt: skip

            parent_widget = target_widget.parentWidget()
            layout = parent_widget.layout() if parent_widget else None

            if not isinstance(layout, QLayout):
                return

            # Find the index of the target widget within the layout
            target_index = -1
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget() == target_widget:
                    target_index = i
                    break

            if target_index == -1:
                return

            config = get_rebuild_config()
            auto_rebuild_checkbox = QCheckBox(f"Auswahlstapel automatisch organisieren (Ankizin)") # fmt: skip
            auto_rebuild_checkbox.setChecked(config.get("autoRebuildDecksOnStartup", True)) # fmt: skip
            auto_rebuild_checkbox.setToolTip(
                "Wenn du diese Option aktivierst, werden Auswahlstapel "
                "automatisch bei jedem Anki-Start neu erstellt"
            )
            qconnect(
                auto_rebuild_checkbox.stateChanged,
                on_auto_rebuild_checkbox_changed,
            )
            layout.insertWidget(target_index + 1, auto_rebuild_checkbox)

        except Exception as e:
            print(f"Ankizin Settings Hook error': {e}")

    aqt.forms.preferences.Ui_Preferences.setupUi = preferences_ui_with_ankizin


def menu_init():
    menu = get_ankizin_menu()
    menu.addSeparator()
    add_lernplan_manager(menu)
    add_lerntag_deck_creator(menu)
    menu.addSeparator()
    init_ankizin_helper(menu)

    # Setup preferences hook
    setup_rebuild_settings_toggle()
