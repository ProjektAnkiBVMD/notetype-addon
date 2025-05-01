from aqt import gui_hooks, mw
from aqt.qt import *
from anki import hooks
import datetime
from pathlib import Path
from aqt.operations.scheduling import add_or_update_filtered_deck
from anki.scheduler import FilteredDeckForUpdate
from aqt.operations import QueryOp
from .menu import get_rebuild_config
from .lernplan_manager import (
    create_lerntag_deck,
    create_previous_lerntag_decks,
    create_lerntag_due_deck,
    remove_previous_lerntag_decks,
)

from .browser import filtered_deck_hk

from ..gui.projekt_anki_menu import get_ankizin_menu

ADDON_DIR_NAME = str(Path(__file__).parent.parent.name)


def lernplan_auto_create():
    # Set up the lernplan
    # Check if the lernplan is already set up / config is available
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if conf is not None and "lernplan" in conf:
        lernplan_conf = conf["lernplan"]

        # Check if the lernplan should be autocreated
        if not lernplan_conf.get("autocreate", False):
            return

        # Check if the lernplan is outdated and it is after rollover
        rollover = mw.col.get_config("rollover")  # returns int, e.g. 4 for 4am
        last_updated = datetime.datetime.fromisoformat(
            lernplan_conf["last_updated"]
        ).date()
        now = datetime.datetime.now()
        today = now.date()

        # Adjust date for rollover - if before rollover time, still considered previous day
        if now.hour < rollover:
            today = today - datetime.timedelta(days=1)

        if not last_updated < today:
            return  # Lernplan is up to date

        # Check if this weekday is in the list of weekdays
        weekdays = lernplan_conf["wochentage"]
        today_weekday = today.weekday()
        if not weekdays[today_weekday]:
            return  # Today is not a lernplan day

        # Increase the Lerntag
        lerntag = int(lernplan_conf.get("lerntag", "001"))
        lerntag += 1
        if lerntag > 85:
            return  # Lernplan is finished

        # Save the config
        lerntag = str(lerntag).zfill(3)
        lernplan_conf["lerntag"] = lerntag
        lernplan_conf["last_updated"] = today.isoformat()
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)

        # Get the yield settings
        highyield = lernplan_conf.get("highyield", False)
        lowyield = lernplan_conf.get("lowyield", False)

        # Remove previous filtered decks
        remove_previous_lerntag_decks()

        # Create the filtered deck
        create_lerntag_deck(lerntag, highyield, lowyield)

        # Create the previous filtered decks if necessary
        if lernplan_conf.get("autocreate_due", False):
            # Create the previous filtered decks
            create_lerntag_due_deck(lerntag, highyield, lowyield)

        if lernplan_conf.get("autocreate_previous", False):
            create_previous_lerntag_decks(lerntag, highyield, lowyield)

        print("Lernplan updated")

    else:
        # Lernplan is not set up
        return None

def try_rebuild_filtered_deck(filtered_deck: FilteredDeckForUpdate):
    searchterm_entry = filtered_deck.config.search_terms[0]
    if "is:new" in searchterm_entry.search or "is:due" in searchterm_entry.search: # already finetuned
        print("deck alread yhas filter")
        mw.col.sched.rebuild_filtered_deck(filtered_deck.id)
    else:
        # rebuild with is:new or is:due filter
        print("Rebuilding deck with is:new or is:due filter")
        searchterm_entry.search = f"{searchterm_entry.search} (is:new or is:due)"
        add_or_update_filtered_deck(parent=mw, deck=filtered_deck).run_in_background()
            
def auto_rebuild_filtered_decks():
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    mw.progress.start()

    config = get_rebuild_config()
    rebuild_all = config.get("autoRebuildDecksOnStartup", True)
    print("Auto rebuild filtered decks (Ankizin):", rebuild_all)
    # match only decks that have "REBUILD" in their name
    for deck in mw.col.decks.all_names_and_ids():
        if col.decks.is_filtered(deck.id):
            if "REBUILD" in deck.name:
                col.sched.rebuild_filtered_deck(deck.id)
            elif rebuild_all:
                # rebuild with is:new or is:due filter
                print(f"Rebuilding deck {deck.name} with is:new or is:due filter")
                # QueryOp(
                #     parent=mw,
                #     op=lambda col: col.sched.get_or_create_filtered_deck(deck_id=deck.id),
                #     success=try_rebuild_filtered_deck,
                # ).run_in_background()
                deck_res =col.sched.get_or_create_filtered_deck(deck_id=deck.id)
                deck_res.allow_empty = True # for some reason this is not set when i call get_or_create_filtered_deck?! no time to investigate
                try_rebuild_filtered_deck(deck_res)

    mw.progress.finish()
    mw.reset()


def profile_loaded_hk():
    lernplan_auto_create()
    auto_rebuild_filtered_decks()
    


def hooks_init():
    gui_hooks.profile_did_open.append(profile_loaded_hk)
    gui_hooks.browser_sidebar_will_show_context_menu.append(filtered_deck_hk)
