"""Smart Filtered Decks & Direct Card Activation for Ankizin Study Hub.

Provides two clean study workflows without ever forcing the user to open Anki's
Browser:
1. Direct activation (`unsuspend_matching_cards`, `suspend_matching_cards`,
   `keep_only_high_yield`) inside the user's Ankizin home deck.
2. Smart Filtered Decks (`daily` auto-rebuild with `is:new OR is:due`, or
   `auto_clean` temporary study deck that removes itself automatically once all
   cards inside have been studied and returned to Ankizin).

Uses `ankizin.compat` so every operation works on Anki 2.1.50 through today.
"""
from __future__ import annotations

import datetime
import html as _html
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, Sequence

from anki.collection import Collection, OpChanges
from anki.errors import AnkiError

from ..compat import (
    begin_undo_entry,
    create_or_update_filtered_deck,
    empty_filtered_deck,
    finish_undo_entry,
    is_filtered_deck,
)
from .tag_index import _LEICHT_PATTERNS, _STARK_PATTERNS, _or_tags

SMART_DECK_PREFIX = "📌 Ankizin: "
FILTERED_LIMIT = 99999
ORDER_ADDED = 5
LARGE_BATCH_CONFIRM_THRESHOLD = 500


@dataclass
class SmartDeckResult:
    created: bool
    deck_id: int = 0
    deck_name: str = ""
    card_count: int = 0
    unsuspended_count: int = 0
    message: str = ""
    changes: OpChanges = field(default_factory=OpChanges)


@dataclass
class SmartDeckInfo:
    deck_id: int
    name: str
    lifecycle: str  # "daily" | "auto_clean"
    yield_preset: str
    remaining_cards: int
    total_matching: int
    created_at: str = ""


@dataclass
class SmartMaintenanceResult:
    rebuilt: list[str] = field(default_factory=list)
    auto_cleaned: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    changed_conf: bool = False
    changes: OpChanges = field(default_factory=OpChanges)


@dataclass
class DailyNewLimitInfo:
    daily_limit: int = 0
    total_active_new: int = 0
    deck_name: str = "Ankizin"


# ── Mode A: Direct Unsuspend / Suspend / Post-Exam Trim ──────────────────────

def _filter_cids_by_queue(col: Collection, cids: Sequence[int], suspended_only: bool) -> list[int]:
    """Return subset of `cids` whose current queue is suspended (`-1`) or active (`!= -1`)."""
    unique = sorted({int(c) for c in cids if c})
    if not unique:
        return []
    op_sql = "queue = -1" if suspended_only else "queue != -1"
    matched: list[int] = []
    chunk_size = 500
    for i in range(0, len(unique), chunk_size):
        chunk = unique[i : i + chunk_size]
        id_sql = ",".join(str(cid) for cid in chunk)
        matched.extend(int(r) for r in col.db.list(f"SELECT id FROM cards WHERE {op_sql} AND id IN ({id_sql})"))
    return matched


def unsuspend_card_ids(
    col: Collection,
    cids: Sequence[int],
    label: str = "Ankizin-Karten freischalten",
) -> tuple[list[int], OpChanges]:
    """Unsuspend pre-indexed suspended card IDs directly in ONE undo step (zero find_cards)."""
    actual = _filter_cids_by_queue(col, cids, suspended_only=True)
    if not actual:
        return [], OpChanges()
    target = begin_undo_entry(col, label)
    col.sched.unsuspend_cards(actual)
    return actual, finish_undo_entry(col, target, card=True, study_queues=True)


def suspend_card_ids(
    col: Collection,
    cids: Sequence[int],
    label: str = "Ankizin-Karten pausieren",
) -> tuple[list[int], OpChanges]:
    """Suspend pre-indexed active card IDs directly in ONE undo step (zero find_cards)."""
    actual = _filter_cids_by_queue(col, cids, suspended_only=False)
    if not actual:
        return [], OpChanges()
    target = begin_undo_entry(col, label)
    col.sched.suspend_cards(actual)
    return actual, finish_undo_entry(col, target, card=True, study_queues=True)


def estimate_study_days(new_cards: int, daily_limit: int) -> Optional[int]:
    """Ceiling estimate of study days for `new_cards` at `daily_limit` new cards/day."""
    if new_cards <= 0 or daily_limit <= 0 or daily_limit >= 9999:
        return None
    return math.ceil(new_cards / daily_limit)


def unsuspend_matching_cards_detailed(col: Collection, search: str) -> tuple[list[int], OpChanges]:
    """Unsuspend all suspended cards matching `search` in ONE undo step and return their IDs."""
    if not search:
        return [], OpChanges()
    cids = col.find_cards(f"({search}) is:suspended")
    if not cids:
        return [], OpChanges()
    target = begin_undo_entry(col, "Ankizin-Karten freischalten")
    col.sched.unsuspend_cards(cids)
    return list(cids), finish_undo_entry(col, target, card=True, study_queues=True)


def unsuspend_matching_cards(col: Collection, search: str) -> tuple[int, OpChanges]:
    """Unsuspend all suspended cards matching `search` in ONE undo step."""
    cids, changes = unsuspend_matching_cards_detailed(col, search)
    return len(cids), changes


def _deck_new_limit(col: Collection, deck: dict) -> int:
    did = deck.get("id")
    if did is None:
        return 0
    preset_limit = 0
    try:
        cfg = col.decks.config_dict_for_deck_id(did)
        if isinstance(cfg, dict):
            preset_limit = int(((cfg.get("new") or {}).get("perDay")) or 0)
    except Exception:
        preset_limit = 0
    raw_override = deck.get("newLimit")
    if isinstance(raw_override, int) and raw_override > 0:
        return min(raw_override, preset_limit) if preset_limit > 0 else raw_override
    return preset_limit


def get_daily_new_limit_info(
    col: Optional[Collection],
    sample_cids: Sequence[int] = (),
) -> DailyNewLimitInfo:
    """Inspect the active daily new-card limit and queued active new cards for Ankizin."""
    if col is None:
        return DailyNewLimitInfo()

    target_did: Optional[int] = None
    if sample_cids:
        deck_counts: Counter[int] = Counter()
        for cid in list(sample_cids)[:25]:
            try:
                card = col.get_card(cid)
                deck_counts[int(card.odid or card.did)] += 1
            except Exception:
                continue
        if deck_counts:
            target_did = deck_counts.most_common(1)[0][0]

    if not target_did:
        target_did = col.decks.id_for_name("Ankizin")

    if not target_did:
        sample = col.find_cards("tag:#Ankizin_*")[:1]
        if sample:
            try:
                c = col.get_card(sample[0])
                target_did = int(c.odid or c.did)
            except Exception:
                target_did = None

    if not target_did:
        return DailyNewLimitInfo()

    deck = col.decks.get(target_did, default=False)
    if not deck:
        return DailyNewLimitInfo()

    effective_limit = _deck_new_limit(col, deck)
    root_did = int(target_did)
    root_name = str(deck.get("name") or "Ankizin")

    try:
        parents = col.decks.parents(target_did) or []
    except Exception:
        parents = []

    if parents:
        # Pick shallowest ancestor (top-level Ankizin deck) as display/aggregation root.
        top_parent = min(parents, key=lambda p: str(p.get("name", "")).count("::"))
        if top_parent.get("id") is not None:
            root_did = int(top_parent["id"])
            root_name = str(top_parent.get("name") or root_name)
        for p in parents:
            plim = _deck_new_limit(col, p)
            if plim > 0:
                effective_limit = min(effective_limit, plim) if effective_limit > 0 else plim

    if hasattr(col.decks, "deck_and_child_ids"):
        try:
            all_dids = {int(d) for d in col.decks.deck_and_child_ids(root_did)}
        except Exception:
            all_dids = {root_did}
    else:
        all_dids = {root_did}
        try:
            all_dids.update(int(cid) for _, cid in col.decks.children(root_did))
        except Exception:
            pass

    did_list = ",".join(str(d) for d in sorted(all_dids)) or str(root_did)
    total_active_new = int(
        col.db.scalar(f"SELECT count() FROM cards WHERE did IN ({did_list}) AND queue = 0") or 0
    )
    return DailyNewLimitInfo(
        daily_limit=effective_limit,
        total_active_new=total_active_new,
        deck_name=root_name,
    )


def format_daily_limit_notice(activated_count: int, info: DailyNewLimitInfo) -> str:
    """Return a clear German HTML notice if daily new-card limit caps what appears today."""
    if info.daily_limit <= 0 or info.daily_limit >= 9999:
        return ""
    deck_label = _html.escape(info.deck_name or "Ankizin")
    if activated_count > info.daily_limit:
        rest = activated_count - info.daily_limit
        return (
            f"<b>Warum siehst du heute nicht alle {activated_count} Karten auf einmal?</b><br>"
            f"Dein Tageslimit im Stapel <b>„{deck_label}“</b> steht aktuell auf "
            f"<b>{info.daily_limit} neue Karten pro Tag</b>. Du lernst heute also zuerst "
            f"<b>{info.daily_limit}</b> neue Karten — die übrigen <b>{rest}</b> Karten erscheinen "
            "automatisch an den nächsten Tagen, damit dich die Wiederholungen nicht überrollen.<br>"
            "<small>Tipp: Das Tageslimit kannst du jederzeit in den Stapel-Optionen oder unter "
            "Ankizin → Wartung anpassen.</small>"
        )
    if info.total_active_new > info.daily_limit:
        return (
            f"<b>Hinweis zum Tageslimit:</b> In deinem Stapel <b>„{deck_label}“</b> warten jetzt "
            f"insgesamt <b>{info.total_active_new}</b> neue Karten, dein Tageslimit steht auf "
            f"<b>{info.daily_limit} pro Tag</b>. Du siehst heute daher maximal "
            f"<b>{info.daily_limit}</b> neue Karten — alle weiteren folgen automatisch an den nächsten Tagen."
        )
    return ""


def suspend_matching_cards(col: Collection, search: str) -> tuple[int, OpChanges]:
    """Suspend all currently active cards matching `search` in ONE undo step."""
    if not search:
        return 0, OpChanges()
    cids = col.find_cards(f"({search}) -is:suspended")
    if not cids:
        return 0, OpChanges()
    target = begin_undo_entry(col, "Ankizin-Karten pausieren")
    col.sched.suspend_cards(cids)
    return len(cids), finish_undo_entry(col, target, card=True, study_queues=True)


def keep_only_high_yield(col: Collection, topic_search: str) -> tuple[int, int, OpChanges]:
    """Post-exam cleanup: keep High Yield (01 + 02) active, suspend other active cards."""
    if not topic_search:
        return 0, 0, OpChanges()
    hy_clause = _or_tags(_STARK_PATTERNS + _LEICHT_PATTERNS)
    kept_cids = col.find_cards(f"({topic_search}) -is:suspended {hy_clause}")
    to_suspend = col.find_cards(f"({topic_search}) -is:suspended -{hy_clause}")
    if not to_suspend:
        return len(kept_cids), 0, OpChanges()
    target = begin_undo_entry(col, "Nach Klausur: Nur High Yield behalten")
    col.sched.suspend_cards(to_suspend)
    return len(kept_cids), len(to_suspend), finish_undo_entry(col, target, card=True, study_queues=True)


# ── Mode B: Smart Filtered Decks ─────────────────────────────────────────────

def _smart_search_for_lifecycle(base_search: str, lifecycle: str) -> str:
    if lifecycle == "auto_clean":
        return f"({base_search}) (is:new OR is:due OR is:learn) -is:suspended"
    return f"({base_search}) (is:new OR is:due) -is:suspended"


def _unique_filtered_name(col: Collection, raw_title: str) -> str:
    clean = " ".join(raw_title.strip().split()) or "Auswahl"
    if len(clean) > 64:
        clean = clean[:61].rstrip() + "…"
    base = clean if clean.startswith(SMART_DECK_PREFIX) else f"{SMART_DECK_PREFIX}{clean}"
    candidate = base
    n = 2
    while (existing_id := col.decks.id_for_name(candidate)) is not None:
        if is_filtered_deck(col, existing_id):
            break
        candidate = f"{base} ({n})"
        n += 1
    return candidate


def create_smart_filtered_deck(
    col: Collection,
    conf: dict,
    title: str,
    base_search: str,
    lifecycle: str = "daily",
    yield_preset: str = "high_yield",
) -> SmartDeckResult:
    """Unsuspend matching cards and create/update a tracked Smart Filtered Deck."""
    if not base_search:
        return SmartDeckResult(created=False, message="Keine Themen ausgewählt.")

    if lifecycle not in ("daily", "auto_clean"):
        lifecycle = "daily"

    target = begin_undo_entry(col, "Smart-Lernstapel erstellen")
    deck_name = _unique_filtered_name(col, title)

    to_unsuspend = col.find_cards(f"({base_search}) is:suspended")
    if to_unsuspend:
        col.sched.unsuspend_cards(to_unsuspend)

    smart_search = _smart_search_for_lifecycle(base_search, lifecycle)
    eligible = col.find_cards(f"({smart_search}) -is:buried -deck:filtered")
    if not eligible:
        changes = finish_undo_entry(col, target, card=True, deck=True, study_queues=True)
        return SmartDeckResult(
            created=False,
            deck_name=deck_name,
            unsuspended_count=len(to_unsuspend),
            message=(
                "Aktuell sind keine neuen oder fälligen Karten verfügbar (evtl. heute bereits gelernt "
                "oder schon in einem anderen Auswahlstapel)."
            ),
            changes=changes,
        )

    did = col.decks.id_for_name(deck_name) or 0
    real_did = create_or_update_filtered_deck(
        col,
        did=did,
        name=deck_name,
        search=smart_search,
        limit=FILTERED_LIMIT,
        order=ORDER_ADDED,
        reschedule=True,
        allow_empty=(lifecycle == "daily"),
    )
    count_in_deck = int(col.db.scalar("SELECT count() FROM cards WHERE did = ?", real_did) or 0)

    smart_conf = conf.setdefault("smart_decks", {})
    smart_conf[str(real_did)] = {
        "name": deck_name,
        "base_search": base_search,
        "lifecycle": lifecycle,
        "yield_preset": yield_preset,
        "created_at": datetime.date.today().isoformat(),
    }

    changes = finish_undo_entry(col, target, card=True, deck=True, study_queues=True)
    return SmartDeckResult(
        created=True,
        deck_id=real_did,
        deck_name=deck_name,
        card_count=count_in_deck,
        unsuspended_count=len(to_unsuspend),
        changes=changes,
    )


def maintain_smart_decks(col: Collection, conf: dict, rebuild_daily: bool = True) -> SmartMaintenanceResult:
    """Maintain Smart Filtered Decks:
    - Prune missing / non-filtered stale metadata entries.
    - Rebuild `daily` decks with `is:new OR is:due`.
    - Auto-delete empty `auto_clean` decks (after cards returned to Ankizin).
    """
    result = SmartMaintenanceResult()
    smart_conf = conf.get("smart_decks")
    if not isinstance(smart_conf, dict) or not smart_conf:
        return result

    target = begin_undo_entry(col, "Ankizin Smart-Stapel pflegen")
    to_remove_ids: list[int] = []

    for did_str, meta in list(smart_conf.items()):
        try:
            did = int(did_str)
        except (TypeError, ValueError):
            del smart_conf[did_str]
            result.changed_conf = True
            continue

        deck = col.decks.get(did, default=False)
        if not deck or not is_filtered_deck(col, did):
            del smart_conf[did_str]
            result.changed_conf = True
            continue

        lifecycle = (meta or {}).get("lifecycle", "daily")
        name = deck.get("name") or (meta or {}).get("name") or f"Deck {did}"
        base_search = (meta or {}).get("base_search", "")

        if lifecycle == "auto_clean":
            remaining = int(col.db.scalar("SELECT count() FROM cards WHERE did = ?", did) or 0)
            if remaining == 0:
                to_remove_ids.append(did)
                del smart_conf[did_str]
                result.auto_cleaned.append(name)
                result.changed_conf = True
        elif lifecycle == "daily" and rebuild_daily and base_search:
            try:
                smart_search = _smart_search_for_lifecycle(base_search, "daily")
                create_or_update_filtered_deck(
                    col,
                    did=did,
                    name=name,
                    search=smart_search,
                    limit=FILTERED_LIMIT,
                    order=ORDER_ADDED,
                    reschedule=True,
                    allow_empty=True,
                )
                result.rebuilt.append(name)
            except AnkiError as e:
                result.failed.append((name, str(e)))

    if to_remove_ids:
        safe_ids = [
            d for d in to_remove_ids
            if is_filtered_deck(col, d)
            and (col.db.scalar("SELECT count() FROM cards WHERE did = ?", d) or 0) == 0
        ]
        if safe_ids:
            col.decks.remove(safe_ids)

    result.changes = finish_undo_entry(col, target, card=True, deck=True, study_queues=True)
    return result


def dissolve_smart_deck(col: Collection, conf: dict, did: int) -> bool:
    """Safely empty a Smart Filtered Deck (returning cards to Ankizin) and delete the wrapper."""
    deck = col.decks.get(did, default=False)
    if not deck or not is_filtered_deck(col, did):
        return False
    target = begin_undo_entry(col, "Smart-Stapel auflösen")
    empty_filtered_deck(col, did)
    col.decks.remove([did])
    smart_conf = conf.get("smart_decks")
    if isinstance(smart_conf, dict) and str(did) in smart_conf:
        del smart_conf[str(did)]
    finish_undo_entry(col, target, card=True, deck=True, study_queues=True)
    return True


def list_smart_decks(col: Collection, conf: dict) -> list[SmartDeckInfo]:
    """Return live status of all tracked Smart Filtered Decks."""
    smart_conf = conf.get("smart_decks") or {}
    items: list[SmartDeckInfo] = []
    for did_str, meta in smart_conf.items():
        try:
            did = int(did_str)
        except (TypeError, ValueError):
            continue
        deck = col.decks.get(did, default=False)
        if not deck or not is_filtered_deck(col, did):
            continue
        remaining = int(col.db.scalar("SELECT count() FROM cards WHERE did = ?", did) or 0)
        items.append(
            SmartDeckInfo(
                deck_id=did,
                name=deck["name"],
                lifecycle=(meta or {}).get("lifecycle", "daily"),
                yield_preset=(meta or {}).get("yield_preset", "high_yield"),
                remaining_cards=remaining,
                total_matching=remaining,
                created_at=(meta or {}).get("created_at", ""),
            )
        )
    items.sort(key=lambda i: i.name.lower())
    return items
