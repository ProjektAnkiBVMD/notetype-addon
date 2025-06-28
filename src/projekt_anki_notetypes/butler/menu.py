from pathlib import Path
import aqt
from aqt import mw
from aqt.qt import *
from aqt.qt import qconnect
from aqt.utils import showInfo, askUser, openLink
from aqt.gui_hooks import profile_did_open
import anki
import anki.hooks
import re
import webbrowser
from aqt.utils import showInfo
import aqt.forms.preferences

from .ankizin_helper import AnkizinHelper
from .lernplan_manager import open_lernplan_manager, open_lerntag_deck_creator
from .utils import get_ankizin_versions

from ..gui.projekt_anki_menu import get_ankizin_menu
from ..gui.config_window import note_type_version
from ..notetype_setting_definitions import projekt_anki_notetype_models

ankizin_helper = None

ADDON_DIR_NAME = str(Path(__file__).parent.parent.name)
ADDON_VERSION = "5.4"


def init_ankizin_helper(menu):
    global ankizin_helper
    ankizin_helper = AnkizinHelper()

    # Add menu item
    first_setup = QAction("1️⃣ Ankizin erstmalig installiert?", mw)
    first_setup.triggered.connect(ankizin_helper.run_first_time_setup)

    update_setup = QAction("🔄 Ankizin-Update installiert?", mw)
    update_setup.triggered.connect(ankizin_helper.run_ankizin_update_setup)

    menu.addAction(first_setup)
    menu.addAction(update_setup)

    print("Ankizin helper initialized")


def add_lernplan_manager(menu):
    action = QAction("🧑🏻‍💼 Lernplan-Manager (automatisch)", mw)
    action.triggered.connect(open_lernplan_manager)
    menu.addAction(action)


def add_lerntag_deck_creator(menu):
    action = QAction("✍🏻 Lerntag-Auswahlstapel erstellen (manuell)", mw)
    action.triggered.connect(open_lerntag_deck_creator)
    menu.addAction(action)


def get_rebuild_config():
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)

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

    mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
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


def add_help_items_to_debug(debug_menu):
    """Add help and community items directly to the debug menu."""
    # Add documentation items
    wiki_action = QAction("📑 Ankizin-Wiki", mw)
    wiki_action.triggered.connect(lambda: openLink("https://www.ankizin.de/wiki/"))
    debug_menu.addAction(wiki_action)
    
    hub_action = QAction("⭐️ Ankizin auf AnkiHub", mw)
    hub_action.triggered.connect(lambda: openLink("https://www.ankizin.de/wiki/wie-installiere-ich-ankihub/"))
    debug_menu.addAction(hub_action)
    
    # Add community items
    discord_action = QAction("👾 Discord", mw)
    discord_action.triggered.connect(lambda: openLink("https://discord.com/invite/5DMsDg8Rvu"))
    debug_menu.addAction(discord_action)
    
    insta_action = QAction("📷 Instagram", mw)
    insta_action.triggered.connect(lambda: openLink("https://www.instagram.com/ankizin_bvmd/"))
    debug_menu.addAction(insta_action)
    
    # Add separator before version info
    debug_menu.addSeparator()


def init_version_info(menu):
    """Add version info to a DEBUG submenu."""
    note_version = note_type_version(projekt_anki_notetype_models()[0])
    if not note_version:
        return

    # Create DEBUG submenu
    menu.addSeparator()
    debug_menu = menu.addMenu("🆘 Hilfe + Mehr")

    # Add help items first
    add_help_items_to_debug(debug_menu)

    note_version_info = QAction(f"Notiztyp-Version: {note_version}", mw)
    note_version_info.setEnabled(False)  # Make it non-clickable
    debug_menu.addAction(note_version_info)

    addon_version_info = QAction(f"AddOn-Version: {ADDON_VERSION}", mw)
    addon_version_info.setEnabled(False)  # Make it non-clickable
    debug_menu.addAction(addon_version_info)


def update_version_info():
    menu = get_ankizin_menu()
    ankizin_versions = get_ankizin_versions()
    ankizin_versions_text = "kein Ankizin"
    if ankizin_versions:
        ankizin_versions_text = ", ".join(ankizin_versions)

    # Find DEBUG submenu
    debug_menu = None
    for action in menu.actions():
        if action.text() == "🆘 Hilfe + Mehr" and action.menu():
            debug_menu = action.menu()
            break

    if not debug_menu:
        return

    # Check if action already exists and remove it
    for action in debug_menu.actions():
        if action.text().startswith("Ankizin-Versionen:"):
            debug_menu.removeAction(action)
            break

    ankizin_versions_info = QAction(f"Ankizin-Versionen: {ankizin_versions_text}", mw)
    ankizin_versions_info.setEnabled(False)
    debug_menu.addAction(ankizin_versions_info)


def menu_init():
    menu = get_ankizin_menu()
    menu.addSeparator()
    add_lernplan_manager(menu)
    add_lerntag_deck_creator(menu)
    menu.addSeparator()
    init_ankizin_helper(menu)
    init_version_info(menu)

    # Setup preferences hook
    setup_rebuild_settings_toggle()

    # Update version info after profile load
    profile_did_open.append(update_version_info)
