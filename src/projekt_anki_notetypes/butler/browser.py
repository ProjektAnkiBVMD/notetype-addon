from aqt import mw
from aqt.qt import *
from anki.collection import SearchNode
from aqt.browser import SidebarItem, SidebarTreeView, SidebarItemType

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aqt.browser import SidebarTreeView  # type: ignore

from .utils import create_filtered_deck, get_ankizin_version_string


def filtered_deck_hk(
    _sidebar: "SidebarTreeView",
    menu: QMenu,
    item: SidebarItem,
    _index: QModelIndex,
):
    if item.item_type == SidebarItemType.TAG:
        if not item.full_name.startswith("#Ankizin"):
            return
        menu.addSeparator()
        menu.addAction(
            "Ankizin: Auswahlstapel aus Schlagwort erstellen",
            lambda: create_dyn_deck_from_tag(item, False),
        )
        menu.addAction(
            "Ankizin: Auswahlstapel aus high-yield Inhalten erstellen",
            lambda: create_dyn_deck_from_tag(item, True),
        )
        menu.addAction(
            "Ankizin: Auswahlstapel aus eingesetzten Inhalten erstellen",
            lambda: create_dyn_deck_from_tag(item, False, unsuspend=False),
        )


def create_dyn_deck_from_tag(
    item: SidebarItem, high_yield=False, unsuspend=True
):
    if not item.full_name or len(item.full_name) < 2:
        return

    col = mw.col
    if col is None:
        raise Exception("collection not available")

    search = col.build_search_string(SearchNode(tag=item.full_name))
    deck_name = format_deck_name(item.name)
    
    if high_yield:
        ankizin_version = get_ankizin_version_string()
        high_yield_tag = f"#Ankizin_{ankizin_version}::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)"
        search += f' tag:"{high_yield_tag}"'
        deck_name = "high-yield " + deck_name

    create_filtered_deck(deck_name, search, unsuspend)


def format_deck_name(tagName: str):
    pieces = tagName.split("_")
    if len(pieces) == 1:
        return tagName
    if pieces[0].isnumeric():
        pieces.pop(0)

    return " ".join(pieces)
