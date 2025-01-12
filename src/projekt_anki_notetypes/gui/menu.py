from aqt.qt import QAction

from .projekt_anki_menu import get_ankizin_menu


def setup_menu(func) -> None:
    menu = get_ankizin_menu()
    a = QAction("Ankizin Notiztypen-Konfigurator", menu)
    menu.addAction(a)
    a.triggered.connect(lambda: func())  # type: ignore
