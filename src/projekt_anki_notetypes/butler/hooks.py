from aqt import gui_hooks, mw
from aqt.qt import *
from aqt.browser import SearchContext
from anki import hooks
import datetime
from pathlib import Path
from aqt.operations.scheduling import add_or_update_filtered_deck
from anki.scheduler import FilteredDeckForUpdate
from .menu import get_rebuild_config
from .lernplan_manager import (
    create_lerntag_deck,
    create_previous_lerntag_decks,
    create_lerntag_due_deck,
    remove_previous_lerntag_decks,
)

from .browser import filtered_deck_hk

ADDON_DIR_NAME = str(Path(__file__).parent.parent.name)


def _get_effective_today():
    """Get today's date adjusted for rollover time"""
    rollover = mw.col.get_config("rollover")  # returns int, e.g. 4 for 4am
    now = datetime.datetime.now()
    today = now.date()
    # Adjust date for rollover - if before rollover time, still considered previous day
    if now.hour < rollover:
        today = today - datetime.timedelta(days=1)
    return today


def _extract_yield_settings(lernplan_conf):
    """Extract yield settings from config"""
    return (
        lernplan_conf.get("highyield_stark", lernplan_conf.get("highyield", False)),
        lernplan_conf.get("highyield_leicht", lernplan_conf.get("highyield", False)),
        lernplan_conf.get("lowyield", False),
        lernplan_conf.get("top100", False),
    ) # fmt: skip


def run_today_setup():
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if conf is not None and "lernplan" in conf:
        last_updated = conf["lernplan"].get("last_updated", None)

        if last_updated is None:
            # No last_updated date available, so we assume the setup should be run
            return True

        # Check if the rebuild hooks should be run right now
        last_updated = datetime.datetime.fromisoformat(last_updated).date()
        today = _get_effective_today()

        if last_updated < today:
            return True
        else:
            return False  # Last updated date is today or in the future

    # No config available, so we assume the setup shouldn't be run
    return False


def lernplan_auto_create():
    """Auto-create lernplan decks based on schedule and configuration"""
    # Get configuration
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if not run_today_setup():
        return

    lernplan_conf = conf["lernplan"]

    # Validate prerequisites
    if not lernplan_conf.get("autocreate", False):
        return

    # Check if today is a scheduled lernplan day
    weekdays = lernplan_conf["wochentage"]
    today_weekday = datetime.datetime.now().date().weekday()
    if not weekdays[today_weekday]:
        return  # Today is not a lernplan day

    # Calculate and validate next lerntag
    current_lerntag = int(lernplan_conf.get("lerntag", "001"))
    next_lerntag = current_lerntag + 1
    if next_lerntag > 85:
        return  # Lernplan is finished

    # Update configuration
    lerntag_str = str(next_lerntag).zfill(3)
    lernplan_conf["lerntag"] = lerntag_str
    lernplan_conf["last_updated"] = datetime.datetime.now().isoformat()
    mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)

    # Create decks
    yield_settings = _extract_yield_settings(lernplan_conf)
    remove_previous_lerntag_decks()
    create_lerntag_deck(lerntag_str, *yield_settings)

    if lernplan_conf.get("autocreate_previous", False):
        create_previous_lerntag_decks(lerntag_str, *yield_settings)


def lernplan_due_deck_auto_create():
    """Create due deck daily, independent of lernplan schedule"""
    # Get configuration
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if conf is None or "lernplan" not in conf:
        return

    lernplan_conf = conf["lernplan"]

    # Validate prerequisites
    if not lernplan_conf.get("autocreate_due", False):
        return
    if not lernplan_conf.get("autocreate", False):
        return

    # Check if update is needed today
    last_due_updated = lernplan_conf.get(
        "last_due_updated", lernplan_conf.get("last_updated", None)
    )
    today = _get_effective_today()

    if last_due_updated is not None:
        last_due_date = datetime.datetime.fromisoformat(last_due_updated).date()
        if last_due_date >= today:
            return  # Already updated today

    # Get current lerntag (no advancement for due deck)
    current_lerntag = lernplan_conf.get("lerntag", "001")

    # Update configuration
    lernplan_conf["last_due_updated"] = today.isoformat()
    mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)

    # Create deck
    yield_settings = _extract_yield_settings(lernplan_conf)
    create_lerntag_due_deck(current_lerntag, *yield_settings, silent=True)

    print("Due deck updated")


def try_rebuild_filtered_deck(filtered_deck: FilteredDeckForUpdate):
    searchterm_entry = filtered_deck.config.search_terms[0]
    if (
        "is:new" in searchterm_entry.search
        or "is:due" in searchterm_entry.search
    ):  # already finetuned
        print("Deck already has is:new or is:due filter")
        mw.col.sched.rebuild_filtered_deck(filtered_deck.id)
    else:
        # rebuild with is:new or is:due filter
        print("Rebuilding deck with is:new or is:due filter")
        searchterm_entry.search = (
            f"{searchterm_entry.search} (is:new or is:due)"
        )
        add_or_update_filtered_deck(
            parent=mw, deck=filtered_deck
        ).run_in_background()


def auto_rebuild_filtered_decks():
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    # Check if the setup should be run today
    if not run_today_setup():
        return

    mw.progress.start()

    config = get_rebuild_config()
    rebuild_all = config.get("autoRebuildDecksOnStartup", True)
    print("Auto rebuild filtered decks (Ankizin):", rebuild_all)
    for deck in mw.col.decks.all_names_and_ids():
        if col.decks.is_filtered(deck.id):
            # match only decks that have "REBUILD" in their name
            if "REBUILD" in deck.name:
                col.sched.rebuild_filtered_deck(deck.id)
            elif rebuild_all:
                # rebuild with is:new or is:due filter
                _deck = col.sched.get_or_create_filtered_deck(deck_id=deck.id)
                _deck.allow_empty = True  # for some reason this is not set when get_or_create_filtered_deck is called
                try_rebuild_filtered_deck(_deck)

    mw.progress.finish()
    mw.reset()


# There is a bug in the Amboss website query that accidentally excludes Ankizin notes. We fix it for them here :)
def browser_search_hk(context: SearchContext):  # type: ignore
    search_term = context.search

    target_string = "note:Ankiphil*"

    has_ankiphil = target_string in search_term
    has_amboss_field = "AMBOSS*:" in search_term
    has_ankizin = "note:ProjektAnki*" in search_term

    if has_ankiphil and has_amboss_field and not has_ankizin:
        replacement_string = "(note:Ankiphil* OR note:ProjektAnki*)"

        modified_search_term = search_term.replace(
            target_string, replacement_string, 1
        )
        context.search = modified_search_term


def profile_loaded_hk():
    lernplan_auto_create()
    lernplan_due_deck_auto_create()
    auto_rebuild_filtered_decks()


def hooks_init():
    gui_hooks.profile_did_open.append(profile_loaded_hk)
    hooks.day_did_change.append(profile_loaded_hk)
    gui_hooks.browser_sidebar_will_show_context_menu.append(filtered_deck_hk)
    gui_hooks.browser_will_search.append(browser_search_hk)
