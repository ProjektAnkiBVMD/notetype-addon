from typing import Callable, Optional

from aqt.qt import QAction

from .projekt_anki_menu import get_ankizin_menu

_notetypes_config_callback: Optional[Callable[[], None]] = None


def get_notetypes_config_callback() -> Optional[Callable[[], None]]:
    return _notetypes_config_callback


def setup_menu(func) -> None:
    global _notetypes_config_callback
    _notetypes_config_callback = func

