from aqt import gui_hooks, mw
from aqt.qt import *
from anki import hooks
import datetime
from pathlib import Path
from .lernplan_manager import (
    create_lerntag_deck,
    create_previous_lerntag_decks,
    remove_previous_lerntag_decks,
)

from .browser import filtered_deck_hk

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
        if lernplan_conf.get("autocreate_previous", False):
            create_previous_lerntag_decks(lerntag, highyield, lowyield)

        print("Lernplan updated")

    else:
        # Lernplan is not set up
        return None


def auto_rebuild_filtered_decks():
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    mw.progress.start()

    # match only decks that have "REBUILD" in their name
    for deck in mw.col.decks.all_names_and_ids():
        if "REBUILD" in deck.name and col.decks.is_filtered(deck.id):
            col.sched.rebuild_filtered_deck(deck.id)

    mw.progress.finish()
    mw.reset()


def profile_loaded_hk():
    lernplan_auto_create()
    auto_rebuild_filtered_decks()


def hooks_init():
    gui_hooks.profile_did_open.append(profile_loaded_hk)
    gui_hooks.browser_sidebar_will_show_context_menu.append(filtered_deck_hk)
