"""Compatibility shims for Anki 2.1.50 through modern Anki (23.10–26.x) & Qt5/Qt6."""
from __future__ import annotations

from typing import Any, Optional, Sequence

from anki.collection import Collection, OpChanges
from anki.errors import AnkiError
from anki.models import ModelManager


def add_compat_aliases():
    add_compat_alias(ModelManager, "by_name", "byName")
    add_compat_alias(ModelManager, "add_dict", "add")
    add_compat_alias(ModelManager, "update_dict", "save")
    add_compat_alias(Collection, "get_note", "getNote")


def add_compat_alias(namespace, new_name, old_name):
    if new_name not in dir(namespace):
        setattr(namespace, new_name, getattr(namespace, old_name))
        return True

    return False


def make_op_changes(**kwargs: bool) -> OpChanges:
    """Construct OpChanges setting only fields present on this Anki version's protobuf."""
    changes = OpChanges()
    for key, val in kwargs.items():
        if hasattr(changes, key):
            try:
                setattr(changes, key, bool(val))
            except Exception:
                pass
    return changes


def is_filtered_deck(col: Collection, did: int) -> bool:
    """True when `did` is a filtered/dynamic deck (Anki 2.1.50+ safe)."""
    if hasattr(col.decks, "is_filtered"):
        return bool(col.decks.is_filtered(did))
    deck = col.decks.get(did, default=False)
    return bool(deck and deck.get("dyn"))


def empty_filtered_deck(col: Collection, did: int) -> None:
    """Empty a filtered deck across Anki 2.1.50–26.x."""
    if hasattr(col.sched, "empty_filtered_deck"):
        col.sched.empty_filtered_deck(did)
    elif hasattr(col.sched, "emptyDyn"):
        col.sched.emptyDyn(did)


def rebuild_filtered_deck(col: Collection, did: int) -> None:
    """Rebuild a filtered deck across Anki 2.1.50–26.x."""
    if hasattr(col.sched, "rebuild_filtered_deck"):
        col.sched.rebuild_filtered_deck(did)
    elif hasattr(col.sched, "rebuildDyn"):
        col.sched.rebuildDyn(did)


def create_or_update_filtered_deck(
    col: Collection,
    did: int,
    name: str,
    search: str,
    limit: int = 99999,
    order: int = 5,
    reschedule: bool = True,
    allow_empty: bool = True,
) -> int:
    """Create or update a filtered deck safely across Anki 2.1.50–26.x. Returns deck id."""
    if hasattr(col.sched, "get_or_create_filtered_deck") and hasattr(col.sched, "add_or_update_filtered_deck"):
        from anki.decks import FilteredDeckConfig

        fdeck = col.sched.get_or_create_filtered_deck(did or 0)
        fdeck.name = name
        if hasattr(fdeck, "allow_empty"):
            fdeck.allow_empty = bool(allow_empty)
        fdeck.config.reschedule = bool(reschedule)
        del fdeck.config.delays[:]
        del fdeck.config.search_terms[:]
        fdeck.config.search_terms.append(
            FilteredDeckConfig.SearchTerm(search=search, limit=limit, order=order)
        )
        col.sched.add_or_update_filtered_deck(fdeck)
        return int(col.decks.id_for_name(name) or did or 0)

    # Anki 2.1.50–2.1.59 fallback
    if did:
        deck = col.decks.get(did, default=False)
    else:
        did = int(col.decks.new_filtered(name))
        deck = col.decks.get(did, default=False)
    if not deck:
        return 0
    deck["name"] = name
    deck["resched"] = bool(reschedule)
    deck["terms"] = [[search, int(limit), int(order)]]
    deck["delays"] = None
    col.decks.save(deck)
    rebuild_filtered_deck(col, did)
    return int(did)


def begin_undo_entry(col: Collection, label: str) -> Optional[int]:
    """Start a custom undo entry if supported (Anki 2.1.55+), else None."""
    if hasattr(col, "add_custom_undo_entry"):
        try:
            return col.add_custom_undo_entry(label)
        except Exception:
            return None
    return None


def finish_undo_entry(col: Collection, target: Optional[int], **fallback_flags: bool) -> OpChanges:
    """Merge a custom undo entry safely without crashing on Anki 2.1.50 or cleared stacks."""
    if target is not None and hasattr(col, "merge_undo_entries"):
        try:
            return col.merge_undo_entries(target)
        except AnkiError:
            pass
    return make_op_changes(**(fallback_flags or {"card": True, "deck": True}))


def update_deck_preset(col: Collection, preset: dict) -> None:
    if hasattr(col.decks, "update_config"):
        col.decks.update_config(preset)
    elif hasattr(col.decks, "save"):
        col.decks.save(preset)


def set_deck_preset(col: Collection, deck_dict: dict, preset_id: int) -> None:
    if hasattr(col.decks, "set_config_id_for_deck_dict"):
        col.decks.set_config_id_for_deck_dict(deck_dict, preset_id)
    else:
        deck_dict["conf"] = preset_id
        col.decks.save(deck_dict)


def set_card_flag(col: Collection, flag: int, cids: Sequence[int]) -> None:
    if not cids:
        return
    if hasattr(col, "set_user_flag_for_cards"):
        col.set_user_flag_for_cards(flag, cids)
    else:
        for cid in cids:
            card = col.get_card(cid)
            card.set_user_flag(flag)
            col.update_card(card)


def remove_empty_cards(col: Collection, cids: Sequence[int]) -> None:
    if not cids:
        return
    if hasattr(col, "remove_cards_and_orphaned_notes"):
        col.remove_cards_and_orphaned_notes(cids)
    elif hasattr(col, "remCards"):
        col.remCards(cids)


def create_backup_now(mw_obj: Any) -> None:
    if mw_obj is None:
        return
    if hasattr(mw_obj, "create_backup_now"):
        mw_obj.create_backup_now()
    elif getattr(mw_obj, "col", None) is not None and hasattr(mw_obj.col, "create_backup"):
        mw_obj.col.create_backup(force=True)


def set_action_no_role(action: Any) -> None:
    """Keep macOS from relocating menu items into the Application Menu (Qt5 & Qt6)."""
    try:
        from aqt.qt import QAction

        if hasattr(QAction, "MenuRole"):
            action.setMenuRole(QAction.MenuRole.NoRole)
        else:
            action.setMenuRole(QAction.NoRole)
    except Exception:
        pass
