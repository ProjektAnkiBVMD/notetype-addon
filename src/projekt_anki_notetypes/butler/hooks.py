from aqt import gui_hooks, mw
from aqt.qt import *
from anki import hooks
import datetime
from pathlib import Path
from .lernplan_manager import create_filtered_deck

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

        # Check if the lernplan is outdated
        last_updated = datetime.datetime.fromisoformat(
            lernplan_conf["last_updated"]
        ).date()
        today = datetime.datetime.today().date()
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

        # Create the filtered deck
        create_filtered_deck(lerntag, highyield, lowyield)
        print("Lernplan updated")

    else:
        # Lernplan is not set up
        return None


def onProfileLoaded():
    lernplan_auto_create()


def hooks_init():
    gui_hooks.profile_did_open.append(onProfileLoaded)
