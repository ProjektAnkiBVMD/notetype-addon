"""Ankizin Setup, Migration & Collection Configuration Engine.

Talks to AnkiCollab (1957538407) and AnkiHub (1322529746) defensively via
try/except wrappers so upstream add-on changes fall back cleanly instead of
crashing, while keeping collection-level operations pure (`col`-accepting)
for deterministic unit testing.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

from anki.collection import Collection, OpChanges

from ..compat import (
    begin_undo_entry,
    empty_filtered_deck,
    finish_undo_entry,
    is_filtered_deck,
    make_op_changes,
    remove_empty_cards,
    set_card_flag,
    set_deck_preset,
    update_deck_preset,
)
from ..constants import ADDON_DIR_NAME

ANKICOLLAB_ADDON_ID = "1957538407"
ANKIHUB_ADDON_ID = "1322529746"
ANKICOLLAB_WEBSITE = "https://ankicollab.com"
ANKICOLLAB_DECK_KEY = "decke-schaufeln-reiche"

STATE_KEY = "ankizin_setup_state"
KEY_OVERRIDE_CONFIG = "ankicollab_deck_key_override"
DEFAULT_PRESET_ID = 1

DELETE_TAG_REGEX = re.compile(
    r"^#Ankizin_v(?:\d+|Ankihub|AnkiCollab)::!DELETE(::(?:update|duplicate))?$",
    re.IGNORECASE,
)

_HIGH_YIELD_STARK_TAGS = (
    "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-*",
    "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)::stark_gelb_M2",
    "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M1_IMPP-Relevanz_(yield)::01-*",
)
_HIGH_YIELD_LEICHT_TAGS = (
    "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::02-*",
    "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)::leicht_gelb_M2",
    "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M1_IMPP-Relevanz_(yield)::02-*",
)

_CONFIG_PATH = Path(__file__).resolve().parent / "ankicollab_config.json"

DEFAULT_SETTINGS = {
    "enabled": True,
    "deck_key": ANKICOLLAB_DECK_KEY,
    "previous_deck_keys": [],
    "deck_name": "Ankizin",
    "ankicollab_addon_id": ANKICOLLAB_ADDON_ID,
    "ankihub_addon_id": ANKIHUB_ADDON_ID,
    "ankihub_deck_ids": [],
    "old_deck_names": ["Ankizin", "Ankizin_v5", "Ankizin_v4", "Ankizin_v3", "Zankiphil"],
}


def _mw():
    import aqt
    return getattr(aqt, "mw", None)


def load_settings() -> dict:
    """Load Ankizin AnkiCollab settings with any local debug key override."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                settings.update(data)
    except (OSError, ValueError):
        pass

    mw = _mw()
    if mw is not None and getattr(mw, "addonManager", None) is not None:
        try:
            conf = mw.addonManager.getConfig(ADDON_DIR_NAME) or {}
            override = conf.get(KEY_OVERRIDE_CONFIG)
            if override:
                settings["deck_key"] = str(override).strip()
                settings["enabled"] = True
        except Exception:
            pass
    return settings


# ── Per-profile wizard state ─────────────────────────────────────────────────

def get_setup_state() -> dict:
    mw = _mw()
    if mw is None or getattr(mw, "pm", None) is None or not isinstance(getattr(mw.pm, "profile", None), dict):
        return {}
    raw = mw.pm.profile.get(STATE_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def update_setup_state(**changes: Any) -> None:
    mw = _mw()
    if mw is None or getattr(mw, "pm", None) is None or not isinstance(getattr(mw.pm, "profile", None), dict):
        return
    state = get_setup_state()
    state.update(changes)
    mw.pm.profile[STATE_KEY] = state
    try:
        mw.pm.save()
    except Exception:
        pass


# ── Other add-ons status ─────────────────────────────────────────────────────

def addon_status(addon_id: str) -> str:
    """Return 'missing' | 'disabled' | 'restart' | 'loaded'."""
    mw = _mw()
    if mw is None or getattr(mw, "addonManager", None) is None:
        return "missing"
    mgr = mw.addonManager
    if addon_id not in mgr.allAddons():
        return "missing"
    if not mgr.isEnabled(addon_id):
        return "disabled"
    if addon_id not in sys.modules:
        return "restart"
    return "loaded"


def _module(addon_id: str, name: str):
    return importlib.import_module(f"{addon_id}.{name}")


# ── AnkiCollab integration ───────────────────────────────────────────────────

def _collab_read_config() -> dict:
    try:
        return _module(ANKICOLLAB_ADDON_ID, "config_manager").get_stored_config() or {}
    except Exception:
        mw = _mw()
        if mw is not None and getattr(mw, "addonManager", None) is not None:
            return mw.addonManager.getConfig(ANKICOLLAB_ADDON_ID) or {}
        return {}


def _collab_write_config(data: dict) -> bool:
    try:
        _module(ANKICOLLAB_ADDON_ID, "config_manager").write_config(data)
        return True
    except Exception:
        mw = _mw()
        if mw is not None and getattr(mw, "addonManager", None) is not None:
            try:
                mw.addonManager.writeConfig(ANKICOLLAB_ADDON_ID, data)
                return True
            except Exception:
                return False
        return False


def collab_subscription(deck_key: str) -> Optional[dict]:
    if addon_status(ANKICOLLAB_ADDON_ID) != "loaded" or not deck_key:
        return None
    details = _collab_read_config().get(deck_key)
    return details if isinstance(details, dict) else None


def collab_carry_over_renamed_key(settings: dict) -> bool:
    key = settings.get("deck_key", "")
    if addon_status(ANKICOLLAB_ADDON_ID) != "loaded" or not key:
        return False
    data = _collab_read_config()
    if isinstance(data.get(key), dict):
        old_entries = [k for k in settings.get("previous_deck_keys", []) if k in data]
        if not old_entries:
            return False
        for old in old_entries:
            del data[old]
    else:
        old = next((k for k in settings.get("previous_deck_keys", []) if isinstance(data.get(k), dict)), None)
        if not old:
            return False
        data[key] = data.pop(old)
    _collab_write_config(data)
    return True


def collab_installed_deck_id(deck_key: str) -> int:
    details = collab_subscription(deck_key)
    if not details:
        return 0
    did = int(details.get("deckId") or 0)
    mw = _mw()
    if did and mw is not None and getattr(mw, "col", None) is not None:
        if mw.col.decks.get(did, default=False):
            return did
    return 0


def collab_is_logged_in() -> bool:
    if addon_status(ANKICOLLAB_ADDON_ID) != "loaded":
        return False
    try:
        return bool(_module(ANKICOLLAB_ADDON_ID, "auth_manager").auth_manager.is_logged_in())
    except Exception:
        return False


def collab_open_login(parent) -> None:
    dialogs = _module(ANKICOLLAB_ADDON_ID, "dialogs")
    dialogs.LoginDialog(parent).exec()
    try:
        _module(ANKICOLLAB_ADDON_ID, "menu").update_ui_for_login_state()
    except Exception:
        pass


def collab_signup_url() -> str:
    try:
        return _module(ANKICOLLAB_ADDON_ID, "var_defs").WEBSITE_BASE_URL + "/signup"
    except Exception:
        return ANKICOLLAB_WEBSITE + "/signup"


def collab_website_base_url() -> str:
    try:
        url = str(_module(ANKICOLLAB_ADDON_ID, "var_defs").WEBSITE_BASE_URL or "").strip()
        if url:
            return url.rstrip("/")
    except Exception:
        pass
    return ANKICOLLAB_WEBSITE.rstrip("/")


def collab_api_base_url() -> str:
    try:
        url = str(_module(ANKICOLLAB_ADDON_ID, "var_defs").API_BASE_URL or "").strip()
        if url:
            return url.rstrip("/")
    except Exception:
        pass
    return "https://plugin.ankicollab.com"


def collab_device_id() -> str:
    try:
        did = str(_module(ANKICOLLAB_ADDON_ID, "config_manager").get_device_id() or "").strip()
        if did:
            return did
    except Exception:
        pass
    return str(uuid.uuid4())


def collab_pairing_url(code: str) -> str:
    try:
        return str(_module(ANKICOLLAB_ADDON_ID, "dialogs").pairing_url(code))
    except Exception:
        return f"{collab_website_base_url()}/pair?code={code}"


def collab_interpret_poll(status_code: int, body: Any) -> str:
    if status_code == 200:
        status = body.get("status") if isinstance(body, dict) else ""
        if status == "approved":
            return "approved"
        if status == "pending":
            return "pending"
        return "retry"
    if status_code == 403:
        return "rejected"
    if status_code in (404, 410):
        return "expired"
    return "retry"


def collab_pair_init(device_id: Optional[str] = None, timeout: int = 10) -> dict:
    if requests is None:
        return {"ok": False, "error": "Netzwerk-Bibliothek (requests) ist nicht verfügbar."}
    try:
        response = requests.post(
            f"{collab_api_base_url()}/pair/init",
            json={"device_id": device_id or collab_device_id()},
            timeout=timeout,
            verify=True,
        )
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                data = {}
            code = str(data.get("code", "")).strip() if isinstance(data, dict) else ""
            poll_token = str(data.get("poll_token", "")).strip() if isinstance(data, dict) else ""
            if code and poll_token:
                try:
                    expires_in = int(data.get("expires_in", 300) or 300)
                except (TypeError, ValueError):
                    expires_in = 300
                return {
                    "ok": True,
                    "code": code,
                    "poll_token": poll_token,
                    "expires_in": expires_in,
                }
        return {
            "ok": False,
            "error": f"AnkiCollab hat die Anfrage abgelehnt ({response.status_code}).",
        }
    except requests.Timeout:
        return {
            "ok": False,
            "error": "AnkiCollab hat nicht rechtzeitig geantwortet. Bitte prüfe deine Internetverbindung.",
        }
    except Exception:
        return {
            "ok": False,
            "error": "AnkiCollab konnte nicht erreicht werden. Bitte prüfe deine Internetverbindung.",
        }


def collab_pair_poll(poll_token: str, timeout: int = 8) -> dict:
    if requests is None:
        return {"outcome": "retry", "body": {}, "token": poll_token}
    try:
        response = requests.post(
            f"{collab_api_base_url()}/pair/poll",
            json={"token": poll_token},
            timeout=timeout,
            verify=True,
        )
        try:
            body = response.json()
        except ValueError:
            body = {}
        return {
            "outcome": collab_interpret_poll(response.status_code, body),
            "body": body,
            "token": poll_token,
        }
    except Exception:
        return {"outcome": "retry", "body": {}, "token": poll_token}


def collab_store_login_result(body: dict) -> bool:
    if addon_status(ANKICOLLAB_ADDON_ID) != "loaded":
        return False
    try:
        ok = bool(_module(ANKICOLLAB_ADDON_ID, "auth_manager").auth_manager.store_login_result(body))
    except Exception:
        return False
    if ok:
        try:
            _module(ANKICOLLAB_ADDON_ID, "menu").update_ui_for_login_state()
        except Exception:
            pass
        try:
            _module(ANKICOLLAB_ADDON_ID, "hooks").refresh_note_status_record()
        except Exception:
            pass
    return ok


def collab_get_settings() -> dict:
    if addon_status(ANKICOLLAB_ADDON_ID) != "loaded":
        return {}
    s = _collab_read_config().get("settings", {})
    return dict(s) if isinstance(s, dict) else {}


def collab_configure_settings(
    pull_on_startup: Optional[bool] = True,
    suspend_new_cards: Optional[bool] = True,
    preserve_deck_structure: Optional[bool] = True,
) -> bool:
    """Configure AnkiCollab global settings cleanly without requiring its modal."""
    if addon_status(ANKICOLLAB_ADDON_ID) != "loaded":
        return False
    data = _collab_read_config()
    settings = data.setdefault("settings", {})
    if not isinstance(settings, dict):
        settings = {}
        data["settings"] = settings
    if pull_on_startup is not None:
        settings["pull_on_startup"] = bool(pull_on_startup)
    if suspend_new_cards is not None:
        settings["suspend_new_cards"] = bool(suspend_new_cards)
    if preserve_deck_structure is not None:
        settings["preserve_deck_structure"] = bool(preserve_deck_structure)
    return _collab_write_config(data)


def collab_subscribe(deck_key: str, on_pulled=None, protected_extra: Optional[list[str]] = None) -> None:
    """Subscribe to Ankizin on AnkiCollab and trigger deck download."""
    mw = _mw()
    data = _collab_read_config()
    if deck_key not in data or not isinstance(data.get(deck_key), dict):
        try:
            protected = list(_module(ANKICOLLAB_ADDON_ID, "var_defs").DEFAULT_PROTECTED_TAGS)
        except Exception:
            protected = ["leech", "marked", "missing-media"]
        for tag in protected_extra or ():
            if tag not in protected:
                protected.append(tag)
        data[deck_key] = {
            "timestamp": "2022-12-31 23:59:59",
            "deckId": 0,
            "optional_tags": {},
            "personal_tags": protected,
        }
        _collab_write_config(data)

    def count_subscription():
        try:
            _module(ANKICOLLAB_ADDON_ID, "identifier").subscribe_to_deck(deck_key)
        except Exception:
            pass

    threading.Thread(target=count_subscription, daemon=True).start()

    import_manager = _module(ANKICOLLAB_ADDON_ID, "import_manager")
    from aqt.operations import QueryOp

    def on_success(result):
        webresult = result[0] if isinstance(result, tuple) and result else result
        try:
            import_manager.import_webresult(result)
        finally:
            if on_pulled:
                on_pulled(bool(webresult))

    def on_failure(exc):
        print(f"Ankizin: AnkiCollab download failed: {exc}")
        if on_pulled:
            on_pulled(False)

    QueryOp(
        parent=mw,
        op=lambda _: import_manager.async_start_pull(deck_key, False),
        success=on_success,
    ).failure(on_failure).with_progress(
        "Lade das Ankizin-Deck über AnkiCollab herunter..."
    ).run_in_background()


def collab_forget_subscription(deck_key: str) -> None:
    data = _collab_read_config()
    if deck_key in data:
        del data[deck_key]
        _collab_write_config(data)


def collab_open_subscriptions() -> None:
    _module(ANKICOLLAB_ADDON_ID, "menu").on_edit_list()


def collab_trigger_update() -> bool:
    """Trigger AnkiCollab deck update check manually."""
    if addon_status(ANKICOLLAB_ADDON_ID) != "loaded":
        return False
    try:
        menu_mod = _module(ANKICOLLAB_ADDON_ID, "menu")
        if hasattr(menu_mod, "async_update"):
            menu_mod.async_update()
            return True
    except Exception as e:
        print(f"Ankizin: couldn't trigger AnkiCollab update: {e}")
    return False


def install_ankicollab(on_done) -> None:
    """Install or re-enable AnkiCollab (1957538407) from AnkiWeb."""
    mw = _mw()
    status = addon_status(ANKICOLLAB_ADDON_ID)
    if status == "disabled":
        mw.addonManager.toggleEnabled(ANKICOLLAB_ADDON_ID, True)
        on_done(True, "")
        return
    if status in ("restart", "loaded"):
        on_done(True, "")
        return

    from aqt.addons import download_addons, download_encountered_problem, download_log_to_html

    def finished(log):
        if download_encountered_problem(log):
            on_done(False, download_log_to_html(log))
        else:
            on_done(True, "")

    download_addons(mw, mw.addonManager, [int(ANKICOLLAB_ADDON_ID)], finished)


# ── AnkiHub integration ──────────────────────────────────────────────────────

def ankihub_ankizin_decks(settings: Optional[dict] = None) -> list[dict]:
    """Return AnkiHub subscriptions matching Ankizin/Zankiphil."""
    if addon_status(ANKIHUB_ADDON_ID) != "loaded":
        return []
    settings = settings or load_settings()
    try:
        config = _module(ANKIHUB_ADDON_ID, "settings").config
        wanted = {str(u).lower() for u in settings.get("ankihub_deck_ids", [])}
        found = []
        for ah_did in config.deck_ids():
            deck_config = config.deck_config(ah_did)
            name = getattr(deck_config, "name", "") or ""
            lower_name = name.lower()
            if str(ah_did).lower() in wanted or "ankizin" in lower_name or "zankiphil" in lower_name:
                found.append(
                    {
                        "uuid": ah_did,
                        "name": name,
                        "anki_did": int(getattr(deck_config, "anki_id", 0) or 0),
                    }
                )
        return found
    except Exception as e:
        print(f"Ankizin: couldn't read AnkiHub subscriptions: {e}")
        return []


def ankihub_unsubscribe_on_server(ah_did) -> bool:
    try:
        client_mod = _module(ANKIHUB_ADDON_ID, "addon_ankihub_client")
        client_mod.AddonAnkiHubClient().unsubscribe_from_deck(ah_did)
        return True
    except Exception as e:
        print(f"Ankizin: AnkiHub server unsubscribe failed: {e}")
        return False


def ankihub_remove_locally(ah_did) -> None:
    _module(ANKIHUB_ADDON_ID, "main.deck_unsubscribtion").uninstall_deck(ah_did)


# ── Pure Collection helpers ──────────────────────────────────────────────────

def has_ankizin_content(col: Optional[Collection]) -> bool:
    """True when the collection has Ankizin/Zankiphil decks, tags, or ProjektAnki notes."""
    if col is None:
        return False
    for deck in col.decks.all_names_and_ids():
        low = deck.name.lower()
        if "ankizin" in low or "zankiphil" in low:
            return True
    for tag in col.tags.all():
        low = tag.lower()
        if low.startswith("#ankizin") or low.startswith("#zankiphil"):
            return True
    mids = [
        m.id
        for m in col.models.all_names_and_ids()
        if m.name.lower().startswith("projektanki") or "heroldinnereankinick" in m.name.lower()
    ]
    if mids:
        id_list = ",".join(str(int(m)) for m in mids)
        if col.db.scalar(f"SELECT 1 FROM notes WHERE mid IN ({id_list}) LIMIT 1"):
            return True
    return False


def find_ankizin_deck_ids(col: Collection) -> list[int]:
    """Return non-filtered deck IDs belonging to Ankizin notes or named *Ankizin*."""
    dids = set(
        col.db.list(
            "SELECT DISTINCT CASE WHEN odid != 0 THEN odid ELSE did END FROM cards "
            "WHERE nid IN ("
            "  SELECT id FROM notes WHERE tags LIKE '% #Ankizin%' OR tags LIKE '% #Zankiphil%'"
            ")"
        )
    )
    for d in col.decks.all_names_and_ids():
        if is_filtered_deck(col, d.id):
            continue
        low = d.name.lower()
        if ("ankizin" in low or "zankiphil" in low) and "_alt" not in low and "(old copy)" not in low:
            dids.add(d.id)
    return [did for did in dids if did and col.decks.get(did, default=False) and not is_filtered_deck(col, did)]


def find_old_ankizin_decks(col: Optional[Collection], settings: dict, ankihub_decks: list[dict]) -> list[int]:
    if col is None:
        return []
    dids: list[int] = []
    for d in ankihub_decks:
        did = d.get("anki_did")
        if did and col.decks.get(did, default=False):
            name = col.decks.name(did)
            top = col.decks.by_name(name.split("::")[0])
            dids.append(top["id"] if top else did)
    for name in settings.get("old_deck_names", []):
        deck = col.decks.by_name(name)
        if deck and not deck.get("dyn"):
            dids.append(deck["id"])
    return list(dict.fromkeys(dids))


def set_deck_aside(col: Collection, did: int, suffix: str = "_alt") -> str:
    """Rename a deck (e.g. Ankizin -> Ankizin_alt) so AnkiCollab creates a clean deck."""
    top_name = col.decks.name(did).split("::")[0]
    base = f"{top_name}{suffix}"
    name, n = base, 2
    while col.decks.by_name(name):
        name = f"{base} {n}"
        n += 1
    col.decks.rename(did, name)
    return name


def deck_card_count(col: Collection, did: int) -> int:
    ids = ",".join(str(int(d)) for d in col.decks.deck_and_child_ids(did))
    return int(col.db.scalar(f"SELECT count() FROM cards WHERE did IN ({ids}) OR odid IN ({ids})") or 0)


def old_copy_decks(col: Optional[Collection]) -> list[int]:
    if col is None:
        return []
    pattern = re.compile(r"(?:_alt| \(old copy\))(?: \d+)?$")
    return [
        d.id
        for d in col.decks.all_names_and_ids()
        if "::" not in d.name and not is_filtered_deck(col, d.id) and pattern.search(d.name)
    ]


def copy_deck_options(col: Collection, old_did: int, new_did: int) -> int:
    """Copy non-default deck preset IDs from an old deck tree to the new one."""
    old_top = col.decks.name(old_did)
    new_top = col.decks.name(new_did)
    old_presets: dict[str, int] = {}
    for did in col.decks.deck_and_child_ids(old_did):
        deck = col.decks.get(did)
        if deck and not deck.get("dyn"):
            old_presets[deck["name"][len(old_top):]] = deck["conf"]
    fallback = old_presets.get("", DEFAULT_PRESET_ID)

    changed = 0
    for did in col.decks.deck_and_child_ids(new_did):
        deck = col.decks.get(did)
        if not deck or deck.get("dyn") or deck["conf"] != DEFAULT_PRESET_ID:
            continue
        preset = old_presets.get(deck["name"][len(new_top):], fallback)
        if preset != DEFAULT_PRESET_ID and col.decks.get_config(preset):
            deck["conf"] = preset
            col.decks.save(deck)
            changed += 1
    return changed


def empty_ankizin_filtered_decks(col: Collection) -> int:
    """Empty any filtered decks holding Ankizin cards (per wiki migration guide)."""
    emptied = 0
    ankizin_filtered = col.db.list(
        "SELECT DISTINCT did FROM cards WHERE odid != 0 AND nid IN ("
        "  SELECT id FROM notes WHERE tags LIKE '% #Ankizin%' OR tags LIKE '% #Zankiphil%'"
        ")"
    )
    for did in ankizin_filtered:
        if col.decks.get(did, default=False) and is_filtered_deck(col, did):
            empty_filtered_deck(col, did)
            emptied += 1
    return emptied


def find_delete_marked_notes(col: Optional[Collection]) -> tuple[list[int], list[int]]:
    """Return (unlearned_nids, reviewed_nids) for notes carrying an Ankizin !DELETE tag."""
    if col is None:
        return [], []
    nids = col.find_notes(f'"tag:re:{DELETE_TAG_REGEX.pattern}"')
    if not nids:
        return [], []
    id_str = ",".join(str(int(n)) for n in nids)
    reviewed_set = set(
        col.db.list(
            f"SELECT DISTINCT nid FROM cards WHERE nid IN ({id_str}) AND (type != 0 OR reps > 0)"
        )
    )
    unlearned = [nid for nid in nids if nid not in reviewed_set]
    reviewed = [nid for nid in nids if nid in reviewed_set]
    return unlearned, reviewed


def delete_marked_notes(col: Collection, include_reviewed: bool = False) -> tuple[int, int]:
    """Delete !DELETE-tagged notes. Returns (deleted_count, skipped_reviewed_count)."""
    unlearned, reviewed = find_delete_marked_notes(col)
    to_delete = list(unlearned)
    if include_reviewed:
        to_delete.extend(reviewed)
        skipped = 0
    else:
        skipped = len(reviewed)
    if to_delete:
        col.remove_notes(to_delete)
    return len(to_delete), skipped


def apply_recommended_ankizin_settings(
    col: Collection,
    new_per_day: int = 40,
    max_ivl: int = 3600,
) -> dict[str, Any]:
    """Apply Ankizin-recommended FSRS & deck options to a dedicated 'Ankizin' preset."""
    config_settings = {
        "activeCols": ["noteFld", "deck", "noteCrt", "template", "cardDue", "noteMod"],
        "sortType": "noteCrt",
        "sortBackwards": False,
        "noteSortType": "noteCrt",
        "browserNoteSortBackwards": False,
        "newSpread": 1,  # Show new cards after reviews
        "applyAllParentLimits": True,
        "fsrs": True,
    }
    for key, value in config_settings.items():
        col.set_config(key, value)
    try:
        col.set_browser_card_columns(config_settings["activeCols"])
    except Exception:
        pass

    decks = col.decks
    preset = next((c for c in decks.all_config() if c["name"] == "Ankizin"), None)
    created = preset is None
    if preset is None:
        preset = decks.add_config("Ankizin")

    preset["new"]["perDay"] = int(new_per_day)
    preset["rev"]["perDay"] = 9999
    preset["new"]["delays"] = [15.0]
    preset["lapse"]["delays"] = [15.0]
    preset["lapse"]["leechFails"] = 15
    preset["lapse"]["leechAction"] = 1  # tag only
    preset["new"]["order"] = 3
    preset["newSortOrder"] = 1
    preset["newGatherPriority"] = 2
    preset["reviewOrder"] = 4
    preset["newMix"] = 1
    preset["new"]["bury"] = True
    preset["rev"]["bury"] = True
    preset["buryInterdayLearning"] = True
    preset["rev"]["maxIvl"] = int(max_ivl)
    update_deck_preset(col, preset)

    dids = find_ankizin_deck_ids(col)
    assigned = 0
    for did in dids:
        deck_dict = decks.get(did, default=False)
        if deck_dict and not deck_dict.get("dyn"):
            set_deck_preset(col, deck_dict, preset["id"])
            assigned += 1

    return {
        "preset_id": preset["id"],
        "preset_created": created,
        "decks_assigned": assigned,
        "new_per_day": int(new_per_day),
        "max_ivl": int(max_ivl),
    }


def suspend_ankizin_cards(col: Collection, only_new: bool = True) -> int:
    """Suspend Ankizin cards. With only_new=True, existing review progress is left untouched."""
    base = '(tag:#Ankizin_v* OR tag:#Ankizin_* OR tag:#Zankiphil*)'
    query = f"{base} is:new -is:suspended" if only_new else f"{base} -is:suspended"
    cids = col.find_cards(query)
    if cids:
        col.sched.suspend_cards(cids)
    return len(cids)


def flag_high_yield_cards(
    col: Collection,
    stark_flag: int = 1,
    leicht_flag: int = 2,
) -> tuple[int, int]:
    """Flag unflagged High-Yield cards (1=Red for stark gelb, 2=Orange for leicht gelb)."""
    stark_q = " OR ".join(f'"tag:{t}"' for t in _HIGH_YIELD_STARK_TAGS)
    leicht_q = " OR ".join(f'"tag:{t}"' for t in _HIGH_YIELD_LEICHT_TAGS)

    stark_cids = col.find_cards(f"({stark_q}) flag:0")
    if stark_cids:
        set_card_flag(col, stark_flag, stark_cids)

    stark_set = set(stark_cids)
    leicht_cids = [c for c in col.find_cards(f"({leicht_q}) flag:0") if c not in stark_set]
    if leicht_cids:
        set_card_flag(col, leicht_flag, leicht_cids)

    return len(stark_cids), len(leicht_cids)


def detect_personal_tags_on_ankizin(col: Collection) -> list[str]:
    """Find user-created tags on Ankizin notes so AnkiCollab can preserve them."""
    personal: set[str] = set()
    ignored_prefixes = ("#ankizin", "#zankiphil", "ankicollab", "ankihub")
    ignored_exact = {"leech", "marked", "missing-media"}
    for tag in col.tags.all():
        low = tag.lower()
        if low in ignored_exact or any(low.startswith(p) for p in ignored_prefixes):
            continue
        # Only keep if actually attached to an Ankizin note
        escaped = tag.replace("\\", "\\\\").replace('"', r'\"')
        if col.find_notes(f'(tag:#Ankizin_* OR tag:#Zankiphil*) "tag:{escaped}"'):
            personal.add(tag)
    return sorted(personal)


def protect_personal_tags_for_collab(
    col: Optional[Collection],
    deck_key: str,
    predetected_tags: Optional[list[str]] = None,
) -> list[str]:
    """Add user's existing custom tags + AnkiCollab_Personal to AnkiCollab protected tags."""
    if addon_status(ANKICOLLAB_ADDON_ID) != "loaded":
        return []
    personal = list(predetected_tags) if predetected_tags is not None else (
        detect_personal_tags_on_ankizin(col) if col is not None else []
    )
    if "AnkiCollab_Personal" not in personal:
        personal.append("AnkiCollab_Personal")
    data = _collab_read_config()
    entry = data.get(deck_key)
    if isinstance(entry, dict):
        existing = list(entry.get("personal_tags") or [])
        changed = False
        for tag in personal:
            if tag not in existing:
                existing.append(tag)
                changed = True
        if changed:
            entry["personal_tags"] = existing
            _collab_write_config(data)
    return personal


def configure_ankizin_collection(col: Collection, opts: dict) -> dict[str, Any]:
    """Run all chosen post-install collection configuration steps cleanly."""
    summary: dict[str, Any] = {
        "suspended": 0,
        "deleted": 0,
        "skipped_reviewed_deletes": 0,
        "settings": None,
        "flagged_stark": 0,
        "flagged_leicht": 0,
        "empty_cards": 0,
        "changes": OpChanges(),
    }

    # Deck preset add/update resets Anki's undo stack, so run it before opening a custom undo entry.
    if opts.get("apply_settings", True):
        summary["settings"] = apply_recommended_ankizin_settings(
            col,
            new_per_day=int(opts.get("new_per_day", 40)),
            max_ivl=int(opts.get("max_ivl", 3600)),
        )

    target = begin_undo_entry(col, "Ankizin einrichten")
    try:
        if opts.get("delete_marked", True):
            deleted, skipped = delete_marked_notes(
                col,
                include_reviewed=bool(opts.get("include_reviewed_deletes", False)),
            )
            summary["deleted"] = deleted
            summary["skipped_reviewed_deletes"] = skipped

        if opts.get("suspend_cards", True):
            only_new = bool(opts.get("suspend_only_new", True))
            summary["suspended"] = suspend_ankizin_cards(col, only_new=only_new)

        if opts.get("flag_high_yield", False):
            stark, leicht = flag_high_yield_cards(col)
            summary["flagged_stark"] = stark
            summary["flagged_leicht"] = leicht

        col.tags.clear_unused_tags()
        empty_report = col.get_empty_cards()
        if empty_report.notes:
            empty_cids = [c.id for note in empty_report.notes for c in note.cards]
            if empty_cids and opts.get("delete_empty_cards", True):
                remove_empty_cards(col, empty_cids)
                summary["empty_cards"] = len(empty_cids)
    finally:
        summary["changes"] = finish_undo_entry(col, target, card=True, note=True, config=True, deck=True)

    return summary


@dataclass
class OpResult:
    """Wrapper giving any CollectionOp callback the `.changes` attribute Anki expects."""

    value: Any = None
    changes: OpChanges = field(default_factory=OpChanges)


def has_ankizin_preset(col: Optional[Collection]) -> bool:
    if col is None:
        return False
    return any(c.get("name") == "Ankizin" for c in col.decks.all_config())


_TAG_COLLAB_RE = re.compile(r"^#Ankizin_vAnkiCollab(?:::|$)", re.IGNORECASE)
_TAG_ANKIHUB_RE = re.compile(r"^#Ankizin_vAnkihub(?:::|$)", re.IGNORECASE)
_TAG_LEGACY_RE = re.compile(r"^#Ankizin_v(\d+)(?:::|$)", re.IGNORECASE)
_TAG_ZANKI_RE = re.compile(r"^#Zankiphil(?:::|$)", re.IGNORECASE)


def detect_ankizin_tag_sources(col: Optional[Collection]) -> dict[str, Any]:
    """Inspect collection tags to tell AnkiCollab, AnkiHub, and legacy .apkg versions apart."""
    out: dict[str, Any] = {
        "has_collab": False,
        "has_ankihub": False,
        "has_legacy_apkg": False,
        "legacy_versions": [],
    }
    if col is None:
        return out

    legacy_nums: set[int] = set()
    has_zanki = False
    for tag in col.tags.all():
        if _TAG_COLLAB_RE.match(tag):
            out["has_collab"] = True
        elif _TAG_ANKIHUB_RE.match(tag):
            out["has_ankihub"] = True
        elif m := _TAG_LEGACY_RE.match(tag):
            legacy_nums.add(int(m.group(1)))
        elif _TAG_ZANKI_RE.match(tag):
            has_zanki = True

    versions = [f"v{n}" for n in sorted(legacy_nums, reverse=True)]
    if has_zanki:
        versions.append("Zankiphil")
    out["legacy_versions"] = versions
    out["has_legacy_apkg"] = bool(versions)
    return out


# ── Unified Setup Detection ──────────────────────────────────────────────────

def detect_setup_state(
    settings: Optional[dict] = None,
    col: Optional[Collection] = None,
    collab_override: Optional[dict] = None,
    ankihub_override: Optional[list[dict]] = None,
    ankiweb_override: Optional[bool] = None,
    state_override: Optional[dict] = None,
) -> dict[str, Any]:
    """Inspect user environment and classify into:
    'new' | 'migrate_ankihub' | 'migrate_apkg' | 'dual' | 'incomplete' | 'ready'.
    """
    settings = settings or load_settings()
    key = settings.get("deck_key", ANKICOLLAB_DECK_KEY)
    mw = _mw()
    if col is None and mw is not None:
        col = getattr(mw, "col", None)

    if collab_override is None:
        try:
            collab_carry_over_renamed_key(settings)
        except Exception:
            pass
        collab_stat = addon_status(ANKICOLLAB_ADDON_ID)
        logged_in = collab_stat == "loaded" and collab_is_logged_in()
        subscribed = collab_subscription(key) is not None
        installed_did = collab_installed_deck_id(key)
        collab_settings = collab_get_settings()
    else:
        collab_stat = collab_override.get("status", "missing")
        logged_in = bool(collab_override.get("logged_in", False))
        subscribed = bool(collab_override.get("subscribed", False))
        installed_did = int(collab_override.get("installed_did", 0))
        collab_settings = dict(collab_override.get("settings", {}))

    ankihub_decks = ankihub_ankizin_decks(settings) if ankihub_override is None else list(ankihub_override)
    tag_sources = detect_ankizin_tag_sources(col)
    has_content = has_ankizin_content(col)
    state = get_setup_state() if state_override is None else dict(state_override)
    preset_ready = has_ankizin_preset(col)
    configured = bool(state.get("configured") or state.get("finished") or preset_ready)

    on_collab = tag_sources["has_collab"] or (subscribed and installed_did != 0)
    on_ankihub = bool(ankihub_decks) or tag_sources["has_ankihub"]

    if (subscribed or tag_sources["has_collab"]) and ankihub_decks:
        scenario = "dual"
    elif on_collab:
        # Already on #Ankizin_vAnkiCollab — in a good spot, no installation wizard needed
        scenario = "ready"
    elif on_ankihub:
        scenario = "migrate_ankihub"
    elif tag_sources["has_legacy_apkg"] or has_content:
        scenario = "migrate_apkg"
    elif subscribed and installed_did == 0:
        scenario = "incomplete"
    else:
        scenario = "new"

    if ankiweb_override is None:
        ankiweb = bool(mw is not None and getattr(mw, "pm", None) is not None and mw.pm.sync_auth())
    else:
        ankiweb = bool(ankiweb_override)

    old_decks = find_old_ankizin_decks(col, settings, ankihub_decks) if not subscribed else []

    return {
        "scenario": scenario,
        "settings": settings,
        "deck_key": key,
        "collab_status": collab_stat,
        "collab_logged_in": logged_in,
        "subscribed": subscribed,
        "installed_did": installed_did,
        "collab_settings": collab_settings,
        "ankihub_decks": ankihub_decks,
        "tag_sources": tag_sources,
        "has_content": has_content,
        "old_decks": old_decks,
        "configured": configured,
        "preset_ready": preset_ready,
        "ankiweb": ankiweb,
    }


# ── AnkiWeb Sync helper ──────────────────────────────────────────────────────

def sync_ankiweb(on_done, upload_if_asked: bool = False) -> None:
    """Trigger AnkiWeb sync, handling post-migration full upload safely."""
    import aqt.sync as anki_sync
    from aqt import gui_hooks
    from aqt.qt import QTimer

    mw = _mw()
    if mw is None or not getattr(mw, "pm", None) or not mw.pm.sync_auth():
        on_done("no_account")
        return

    original_full_sync = anki_sync.full_sync
    original_handle_error = anki_sync.handle_sync_error
    outcome = {"result": "ok"}

    def full_sync(mw_, out, done):
        outcome["result"] = "full"
        if upload_if_asked and out.required == out.FULL_SYNC:
            server_usn = out.server_media_usn if mw_.pm.media_syncing_enabled() else None
            mw_.closeAllWindows(lambda: anki_sync.full_upload(mw_, server_usn, done))
        else:
            original_full_sync(mw_, out, done)

    def handle_sync_error(mw_, err):
        outcome["result"] = "error"
        original_handle_error(mw_, err)

    def restore():
        anki_sync.full_sync = original_full_sync
        anki_sync.handle_sync_error = original_handle_error
        try:
            gui_hooks.sync_did_finish.remove(finished)
        except ValueError:
            pass

    def finished():
        def later():
            restore()
            on_done(outcome["result"])

        QTimer.singleShot(0, later)

    anki_sync.full_sync = full_sync
    anki_sync.handle_sync_error = handle_sync_error
    gui_hooks.sync_did_finish.append(finished)
    try:
        sync = getattr(mw, "_sync_collection_and_media", None)
        if sync:
            sync(getattr(mw, "_refresh_after_sync", lambda: None))
        else:
            mw.on_sync_button_clicked()
    except Exception:
        restore()
        raise
