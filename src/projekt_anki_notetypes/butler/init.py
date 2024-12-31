import datetime
from pathlib import Path

from aqt import mw

from .lernplan_manager import create_filtered_deck
from .menu import menu_init

ADDON_DIR_NAME = str(Path(__file__).parent.name)


def lernplan_init():
    # Set up the lernplan
    # Check if the lernplan is already set up / config is available
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if conf is not None and "lernplan" in conf:
        lernplan_conf = conf["lernplan"]
        lerntag = lernplan_conf.get("lerntag", 1)
        highyield = lernplan_conf.get("highyield", False)
        lowyield = lernplan_conf.get("lowyield", False)

        # Check if the lernplan is outdated
        last_updated = datetime.datetime.fromisoformat(
            lernplan_conf["last_updated"]
        ).date()
        today = datetime.datetime.today().date()
        if not last_updated < today:
            return # Lernplan is up to date

        # Check if this weekday is in the list of weekdays
        lernplan_started_on = lernplan_conf["lernplan_started_on"]
        weekdays = lernplan_conf["weekdays"]
        today_weekday = today.weekday()
        if not weekdays[today_weekday]:
            return # Today is not a lernplan day

        # Increase the Lerntag
        lerntag += 1
        if lerntag > 85:
            return  # Lernplan is finished

        # Create the filtered deck
        lernplan_conf["lerntag"] = lerntag
        lernplan_conf["last_updated"] = today.isoformat()
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
        create_filtered_deck(lerntag, highyield, lowyield)

    else:
        # Lernplan is not set up
        return None


def init_butler():
    menu_init()
    lernplan_init()