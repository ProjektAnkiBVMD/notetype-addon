from aqt import mw
from aqt.qt import QMenu


# fmt: off
addon_name = __name__.split('.')[0]

MENU_NAME = "&Ankizin"
# fmt: on


def get_ankizin_menu() -> QMenu:
    """Get or create Ankizin menu."""
    menubar = mw.form.menubar

    submenus = menubar.findChildren(QMenu)
    for submenu in submenus:
        if submenu.title() == MENU_NAME:
            menu = submenu
            break
    else:
        menu = menubar.addMenu(MENU_NAME)

    return menu
