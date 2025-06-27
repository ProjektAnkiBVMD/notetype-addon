from aqt import mw
from aqt.qt import *
from anki.collection import SearchNode
from aqt.browser import SidebarItem, SidebarTreeView, SidebarItemType

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aqt.browser import SidebarTreeView  # type: ignore

from .utils import create_filtered_deck


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
            "Ankizin: Auswahlstapel aus Schlagwort erstellen (alle einsetzen)",
            lambda: create_dyn_deck_from_tag(item, high_yield=False),
        )
        menu.addAction(
            "Ankizin: Auswahlstapel aus high-yield Karten erstellen (alle einsetzen)",
            lambda: create_dyn_deck_from_tag(item, high_yield=True),
        )
        menu.addAction(
            "Ankizin: Auswahlstapel nur aus eingesetzten Karten erstellen",
            lambda: create_dyn_deck_from_tag(item, high_yield=False, unsuspend=False),
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
        high_yield_tags = [
            "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)",
            "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-*",
            "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::02-*",
        ]
        high_yield_search = " OR ".join(
            [f'"tag:{tag}"' for tag in high_yield_tags]
        )
        search += f" ({high_yield_search})"
        deck_name += " - high-yield"

    create_filtered_deck(deck_name, search, unsuspend=unsuspend)
    mw.reset()


def format_deck_name(tagName: str):
    pieces = tagName.split("_")
    if len(pieces) == 1:
        return tagName
    if pieces[0].isnumeric():
        pieces.pop(0)

    return " ".join(pieces)
