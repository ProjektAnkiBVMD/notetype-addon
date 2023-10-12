from aqt.qt import QAction

from .projekt_anki_menu import get_anking_menu


def setup_menu(func) -> None:
    menu = get_anking_menu()
    a = QAction("Projekt Anki Notiztypen", menu)
    menu.addAction(a)
    a.triggered.connect(lambda: func())  # type: ignore
