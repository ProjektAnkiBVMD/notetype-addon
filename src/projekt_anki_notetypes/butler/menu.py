from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, askUser
import anki.hooks
import re
import webbrowser
import anki
from aqt.utils import showInfo
from aqt import mw

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
    action = QAction("spezifisches Lerntag-Deck erstellen", mw)
    action.triggered.connect(open_lerntag_deck_creator)
    menu.addAction(action)


def menu_init():
    menu = get_ankizin_menu()
    menu.addSeparator()
    add_lernplan_manager(menu)
    add_lerntag_deck_creator(menu)
    menu.addSeparator()
    init_ankizin_helper(menu)
