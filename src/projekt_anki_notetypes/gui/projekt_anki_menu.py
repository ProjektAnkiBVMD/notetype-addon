from aqt import mw
from aqt.utils import openLink
from aqt.qt import QMenu, QAction


# fmt: off
addon_name = __name__.split('.')[0]

# Increment this after modifying below options.
SUBMENU_VER = 2
MENU_NAME = "&Ankizin"

GET_HELP_MENU_NAME = "Ankizin + Hilfe"
GET_HELP_MENU_OPTIONS = [
    ("Ankizin Webseite", "https://ankizin.de"),
    ("Instagram", "https://www.instagram.com/ankizin_bvmd/"),
    ("Linksammlung", "https://linktr.ee/anki_germany"),
    ("Discord", "https://discord.com/invite/5DMsDg8Rvu"),
]
# fmt: on


def create_get_help_submenu(parent: QMenu) -> QMenu:
    submenu = QMenu(GET_HELP_MENU_NAME, parent)
    for name, url in GET_HELP_MENU_OPTIONS:
        act = QAction(name, mw)
        act.triggered.connect(lambda _, u=url: openLink(u))  # type: ignore
        submenu.addAction(act)
    return submenu


def maybe_add_get_help_submenu(menu: QMenu) -> None:
    """Adds submenu in 'Projekt Anki' menu if needed.

    The submenu is added if:
    - The submenu does not exist in menu
    - The submenu is an outdated version - existing is deleted

    With versioning and projekt_anki_get_help property,
    future version can rename, hide, or change contents in the submenu
    """
    submenu_property = "projekt_anki_get_help"
    for act in menu.actions():
        # Don't replace below with GET_HELP_MENU_NAME
        # so the menu name can be changed in the future.
        # This is for older anking addons that doesn't set submenu_property
        if (
            act.property(submenu_property)
            or act.text() == "Ankizin + Hilfe"
        ):
            ver = act.property("version")
            if ver and ver >= SUBMENU_VER:
                return
            submenu = create_get_help_submenu(menu)
            menu.insertMenu(act, submenu)
            menu.removeAction(act)
            new_act = submenu.menuAction()
            new_act.setProperty(submenu_property, True)
            new_act.setProperty("version", SUBMENU_VER)
            return

    submenu = create_get_help_submenu(menu)
    menu.addMenu(submenu)
    new_act = submenu.menuAction()
    new_act.setProperty(submenu_property, True)
    new_act.setProperty("version", SUBMENU_VER)


def get_ankizin_menu() -> QMenu:
    """Get or create Ankizin menu. Make sure its submenus are up to date."""
    menubar = mw.form.menubar

    submenus = menubar.findChildren(QMenu)
    for submenu in submenus:
        if submenu.title() == MENU_NAME:
            menu = submenu
            break
    else:
        menu = menubar.addMenu(MENU_NAME)

    maybe_add_get_help_submenu(menu)
    return menu
