from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo
import re
import anki
from aqt.utils import showInfo, showWarning
from aqt import mw
from aqt.operations import CollectionOp
from anki.collection import OpChanges

from .utils import async_general_housekeeping, check_ankizin_installation
from .gui import FirstSetupConfigDialog, UpdateConfigDialog


class AnkizinHelper:

    def __init__(self):
        self.DELETE_TAG_PATTERN = re.compile(
            r"#Ankizin_v(?:\d+|Ankihub)::!DELETE(::(?:update|duplicate))?"
        )

        self.delete_outdated_cards = True
        self.update_deck_config = False
        self.suspend_all_cards = True
        self.suspend_new_cards = False

    def set_delete_outdated_cards(self, state):
        self.delete_outdated_cards = state

    def set_update_deck_config(self, state):
        self.update_deck_config = state

    def set_suspend_all_cards(self, state):
        self.suspend_all_cards = state

    def set_suspend_new_cards(self, state):
        self.suspend_new_cards = state

    def find_ankizin_deck(self):
        # Find Ankizin deck by checking where the majority of all cards that have the #Ankizin tag are located
        collection = mw.col
        deck_counts = {}

        # Find all notes with #Ankizin tag
        for card_id in collection.find_cards("tag:#Ankizin_v*"):
            card = collection.get_card(card_id)
            deck_id = card.did
            deck_counts[deck_id] = deck_counts.get(deck_id, 0) + 1

        # Find deck with most Ankizin cards
        if deck_counts:
            max_deck_id = max(deck_counts.items(), key=lambda x: x[1])[0]
            return max_deck_id

        return None

    def delete_marked_cards(self):
        collection = mw.col
        # Delete notes with specific tags
        notes_to_delete = set()
        for note_id in collection.find_notes(""):
            note = collection.get_note(note_id)
            for tag in note.tags:
                if self.DELETE_TAG_PATTERN.match(tag):
                    notes_to_delete.add(note_id)
                    break

        print(f"Deleting {len(notes_to_delete)} notes")
        collection.remove_notes(list(notes_to_delete))

    @staticmethod
    def general_housekeeping():
        async_general_housekeeping()

    def setup_collection_config(self):
        config_settings = {  # https://github.com/ankitects/anki/blob/main/rslib/src/config/bool.rs
            "activeCols": [
                "noteFld",
                "deck",
                "noteCrt",
                "template",
                "cardDue",
                "noteMod",
            ],
            "sortType": "noteCrt",
            "sortBackwards": False,
            "noteSortType": "noteCrt",
            "browserNoteSortBackwards": False,
            "newSpread": 1,  # reviews first
            "applyAllParentLimits": True,
            "fsrs": True,
        }

        def set_config_new_version():
            """Apply settings using set_config() method (newer Anki versions)"""
            for key, value in config_settings.items():
                print(f"Setting config: {key} = {value}")
                mw.col.set_config(key, value)

        def set_config_old_version():
            """Apply settings using conf dictionary (older Anki versions)"""
            for key, value in config_settings.items():
                mw.col.conf[key] = value
            mw.col.setMod()  # deprecated in newer versions

        try:
            set_config_new_version()
        except (AttributeError, TypeError):
            print("The kids scetchy")
            set_config_old_version()

        mw.col.set_browser_card_columns(config_settings["activeCols"])

    def optimize_settings(self):
        print("hello")
        try:
            # Get the default configuration for the ankizin deck
            did = mw.col.decks.id(
                "Ankizin"
            )  # only works for very default default deck idk mabye ill fix it later

            default_conf = mw.col.decks.config_dict_for_deck_id(did)
            print("default conf")
            print(default_conf)

            # Update collection configuration
            self.setup_collection_config()

            print("collection settings updated")

            # Update deck configurations
            if default_conf:
                # New cards settings
                default_conf["new"]["perDay"] = 50

                # Review settings
                default_conf["rev"]["perDay"] = 9999

                # Learning steps
                default_conf["new"]["delays"] = [15.0]  # 15 minutes
                default_conf["lapse"]["delays"] = [
                    15.0
                ]  # 15 minutes for relearning

                # Leech settings
                default_conf["lapse"]["leechFails"] = 15
                default_conf["lapse"]["leechAction"] = 1  # 1 = tag only

                # Display order settings
                default_conf["new"][
                    "order"
                ] = 3  # DeckConfig_Config_NewCardGatherPriority.HIGHEST_POSITION
                default_conf["newSortOrder"] = (
                    1  # Sortierreihenfolge neuer Karten: Sammelreihenfolge (und Sammelreihenfolge ist typischerweise "Stapel")
                )
                default_conf["newGatherPriority"] = 2  # ascending
                default_conf["reviewOrder"] = (
                    4  # DeckConfig_Config_ReviewCardOrder.INTERVALS_DESCENDING
                )
                default_conf["newMix"] = (
                    1  # Reihenfolge Neu/Wiederholung: Nach Wiederholungen anzeigen
                )

                # Sibling settings
                default_conf["new"]["bury"] = True  # Bury new siblings
                default_conf["rev"]["bury"] = True  # Bury review siblings
                default_conf["buryInterdayLearning"] = (
                    True  # Bury interday learning cards
                )

                # Für daniel
                default_conf["rev"]["maxIvl"] = 180  # 180 days
                print("settings updated")
                # Save the configuration
                deckDict = mw.col.decks.get(did)
                mw.col.decks.set_config_id_for_deck_dict(
                    deckDict, default_conf["id"]
                )
                mw.col.decks.save(default_conf)
            else:
                showInfo(
                    "Keine Deck-Einstellung gefunden. Schreib uns gerne auf Discord an."
                )

        except Exception as e:
            print({str(e)})

    def suspend_cards_from_deck(self, cids=[], all=False):
        # Get the deck object
        if all:
            sus_cids = mw.col.find_cards(f"tag:#Ankizin_v*")
            mw.col.sched.suspend_cards(sus_cids)
            return

        # Else suspend the provided cards
        if cids:
            mw.col.sched.suspend_cards(cids)

    def handle_first_time_options(self):
        if self.update_deck_config:
            self.optimize_settings()
        if self.suspend_all_cards:
            self.suspend_cards_from_deck(cids=[], all=True)
        if self.delete_outdated_cards:
            self.delete_marked_cards()

        return OpChanges()  # to silence the collecitonOp

    def handle_update_options(self):
        if self.suspend_new_cards:
            cids = self.find_new_cards_from_update()
            self.suspend_cards_from_deck(cids, all=False)
        if self.delete_outdated_cards:
            self.delete_marked_cards()

        return OpChanges()

    @staticmethod
    def on_success(out: OpChanges) -> None:
        AnkizinHelper.general_housekeeping()  # always run this

    def run_first_time_setup(self):
        # Check if Ankizin is installed
        if not check_ankizin_installation():
            return

        dialog = FirstSetupConfigDialog(mw, self)
        dialog.setFixedSize(dialog.sizeHint())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            CollectionOp(
                parent=mw, op=lambda _: self.handle_first_time_options()
            ).success(AnkizinHelper.on_success).run_in_background()

    def find_new_cards_from_update(self):
        collection = mw.col
        version_pattern = re.compile(r"#Ankizin_v(\d+)::§NEW_CARDS::v\d+")

        # Extract all version numbers from tags
        versions = [
            int(match.group(1))
            for tag in collection.tags.all()
            if (match := version_pattern.match(tag))
        ]

        if not versions:
            return []

        latest_version = max(versions)
        target_tag = (
            f"#Ankizin_v{latest_version}::§NEW_CARDS::v{latest_version}"
        )
        return collection.find_cards(f"tag:{target_tag}")

    def run_ankizin_update_setup(self):
        # Check if Ankizin is installed
        if not check_ankizin_installation():
            return

        # Ask user what they wanna  do
        dialog = UpdateConfigDialog(mw, self)
        dialog.setFixedSize(dialog.sizeHint())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            CollectionOp(
                parent=mw, op=lambda _: self.handle_update_options()
            ).success(AnkizinHelper.on_success).run_in_background()
