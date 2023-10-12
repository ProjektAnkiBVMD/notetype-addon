from aqt import mw
from aqt.utils import openLink
from aqt.qt import QMenu, QAction


# fmt: off
addon_name = __name__.split('.')[0]

# Increment this after modifying below options.
SUBMENU_VER = 2
MENU_NAME = "&Projekt Anki"

GET_HELP_MENU_NAME = "Projekt Anki + Hilfe"
GET_HELP_MENU_OPTIONS = [
    ("Projekt Anki Webseite", "https://anki.bvmd.de"),
    ("Linksammlung", "https://linktr.ee/anki_germany"),
    ("Discord", "https://discord.gg/7vfg8a79e2"),
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
        if act.property(submenu_property) or act.text() == "Projekt Anki + Hilfe":
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


def get_anking_menu() -> QMenu:
    """Get or create AnKing menu. Make sure its submenus are up to date."""
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
