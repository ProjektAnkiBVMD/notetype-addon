import aqt
from aqt import mw
from aqt.qt import *
from aqt.qt import qconnect
from aqt.utils import showInfo, openLink
from aqt.gui_hooks import profile_did_open
import json
import aqt.forms.preferences

from .ankizin_helper import AnkizinHelper
from .lernplan_manager import open_lernplan_manager, open_lerntag_deck_creator
from .utils import get_ankizin_versions

from ..compat import set_action_no_role
from ..constants import ADDON_DIR_NAME, ADDON_VERSION
from ..gui.menu import get_notetypes_config_callback
from ..gui.projekt_anki_menu import get_ankizin_menu
from ..gui.config_window import note_type_version
from ..notetype_setting_definitions import projekt_anki_notetype_models
from ..onboarding.maintenance import open_maintenance_dialog
from ..onboarding.wizard import open_setup_wizard
from ..study_hub.dialog import open_study_hub

ankizin_helper = None
versions_action = None  # filled in after the profile is open


def add_study_hub_action(menu):
    action = QAction("✨ Ankizin Lern-Zentrale", mw)
    action.setShortcut(QKeySequence("Ctrl+Alt+A"))
    set_action_no_role(action)
    action.triggered.connect(lambda: open_study_hub())
    menu.addAction(action)


def add_setup_wizard_action(menu):
    action = QAction("🚀 Einrichtungs-Assistent", mw)
    set_action_no_role(action)
    action.triggered.connect(lambda: open_setup_wizard(force=True))
    menu.addAction(action)


def add_maintenance_action(menu):
    action = QAction("🧹 Wartung & Einstellungen", mw)
    set_action_no_role(action)
    action.triggered.connect(lambda: open_maintenance_dialog())
    menu.addAction(action)


def add_notetypes_config_action(menu):
    cb = get_notetypes_config_callback()
    if cb is not None:
        action = QAction("🗃️ Ankizin Notiztypen-Konfigurator", mw)
        set_action_no_role(action)
        action.triggered.connect(lambda: cb())
        menu.addAction(action)


def init_ankizin_helper(menu):
    global ankizin_helper
    ankizin_helper = AnkizinHelper()

    # Legacy setup helpers preserved under Hilfe + Mehr
    first_setup = QAction("⏩️ Ankizin erstmalig installiert? (Legacy)", mw)
    first_setup.triggered.connect(ankizin_helper.run_first_time_setup)

    update_setup = QAction("🔄 Ankizin-Update installiert? (Legacy)", mw)
    update_setup.triggered.connect(ankizin_helper.run_ankizin_update_setup)

    menu.addAction(first_setup)
    menu.addAction(update_setup)

    print("Ankizin helper initialized")


def add_lernplan_manager(menu):
    action = QAction("💼 Lernplan-Manager (automatisch)", mw)
    action.triggered.connect(open_lernplan_manager)
    menu.addAction(action)


def add_lerntag_deck_creator(menu):
    action = QAction("📝 Lerntag-Auswahlstapel erstellen (manuell)", mw)
    action.triggered.connect(open_lerntag_deck_creator)
    menu.addAction(action)


def get_rebuild_config():
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)

    if conf is None:
        conf = {}

    # Ensure the keys exist, setting the default values if they don't.
    conf.setdefault("autoRebuildDecksOnStartup", True)
    conf.setdefault("autoRebuildOnlyAnkizinDecks", False)

    return conf


def copy_config_to_clipboard():
    conf = get_rebuild_config()
    conf_json = json.dumps(conf, indent=4)
    QApplication.clipboard().setText(conf_json)
    showInfo("Ankizin-Konfiguration wurde in die Zwischenablage kopiert.")


# (config key, label, tooltip) of the checkboxes in Anki's preferences
REBUILD_OPTIONS = (
    (
        "autoRebuildDecksOnStartup",
        "Auswahlstapel automatisch organisieren (Ankizin)",
        "Wenn du diese Option aktivierst, werden Auswahlstapel "
        "automatisch bei jedem Anki-Start neu erstellt",
    ),
    (
        "autoRebuildOnlyAnkizinDecks",
        "…nur Ankizin-Auswahlstapel (meine eigenen nicht anfassen)",
        "Aktiv: nur Lernplan-Stapel und Stapel aus Ankizin-Schlagwörtern. "
        "Aus: alle deine Auswahlstapel, auch selbst erstellte.",
    ),
)


def set_rebuild_option(key: str, checked: bool):
    """Called when the user clicks a checkbox in Preferences."""
    conf = get_rebuild_config()
    conf[key] = checked

    mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
    print("Auto rebuild setting changed:", key, checked)


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
            for offset, (key, text, tooltip) in enumerate(REBUILD_OPTIONS, 1):
                checkbox = QCheckBox(text)
                checkbox.setChecked(config[key])
                checkbox.setToolTip(tooltip)
                qconnect(checkbox.toggled, lambda checked, key=key: set_rebuild_option(key, checked))
                layout.insertWidget(target_index + offset, checkbox)

        except Exception as e:
            print(f"Ankizin Settings Hook error': {e}")

    aqt.forms.preferences.Ui_Preferences.setupUi = preferences_ui_with_ankizin


def add_help_items_to_debug(debug_menu):
    """Add help and community items directly to the debug menu."""
    # Add documentation items
    wiki_action = QAction("📑 Ankizin-Wiki", mw)
    wiki_action.triggered.connect(lambda: openLink("https://www.ankizin.de/wiki/"))
    debug_menu.addAction(wiki_action)
    
    hub_action = QAction("⭐️ Ankizin auf AnkiCollab", mw)
    hub_action.triggered.connect(lambda: openLink("https://www.ankizin.de/wiki/ankicollab-grundlagen-und-installation-von-ankizin/"))
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

    global versions_action
    versions_action = QAction("Ankizin-Versionen: …", mw)
    versions_action.setEnabled(False)
    debug_menu.addAction(versions_action)

    # Add copy button at the end
    debug_menu.addSeparator()
    init_ankizin_helper(debug_menu)
    debug_menu.addSeparator()
    copy_action = QAction("📋 Konfiguration kopieren", mw)
    qconnect(copy_action.triggered, copy_config_to_clipboard)
    debug_menu.addAction(copy_action)


def update_version_info():
    if versions_action:
        versions = get_ankizin_versions()
        versions_action.setText(f"Ankizin-Versionen: {', '.join(versions) if versions else 'kein Ankizin'}")


def menu_init():
    menu = get_ankizin_menu()
    add_study_hub_action(menu)
    add_setup_wizard_action(menu)
    menu.addSeparator()
    add_lernplan_manager(menu)
    add_lerntag_deck_creator(menu)
    menu.addSeparator()
    add_maintenance_action(menu)
    add_notetypes_config_action(menu)
    init_version_info(menu)

    # Setup preferences hook
    setup_rebuild_settings_toggle()

    # Update version info after profile load
    profile_did_open.append(update_version_info)
