from aqt import mw
from aqt.qt import *
import re
from aqt.operations import CollectionOp
from anki.collection import OpChanges

from .utils import async_general_housekeeping, check_ankizin_installation
from .gui import FirstSetupConfigDialog, UpdateConfigDialog


class AnkizinHelper:

    def __init__(self):
        self.DELETE_TAG_PATTERN = re.compile(
            r"^#Ankizin_v(?:\d+|Ankihub|AnkiCollab)::!DELETE(::(?:update|duplicate))?$"
        )

        self.delete_outdated_cards = True
        self.update_deck_config = False
        self.suspend_all_cards = True
        self.suspend_new_cards = True

    def delete_marked_cards(self):
        # tag:re: is matched per tag (case-insensitive, unanchored), so ^ and $ pin it down
        notes_to_delete = mw.col.find_notes(f'"tag:re:{self.DELETE_TAG_PATTERN.pattern}"')
        print(f"Deleting {len(notes_to_delete)} notes")
        mw.col.remove_notes(notes_to_delete)

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

        for key, value in config_settings.items():
            mw.col.set_config(key, value)

        mw.col.set_browser_card_columns(config_settings["activeCols"])

    def optimize_settings(self):
        self.setup_collection_config()

        # Ankizin gets a deck options preset of its own, so the user's other decks keep theirs.
        # Cards in filtered decks count for the deck they came from (odid).
        dids = mw.col.db.list(
            "select distinct case when odid != 0 then odid else did end from cards "
            "where nid in (select id from notes where tags like '% #Ankizin_v%')"
        )
        if not dids:
            return

        decks = mw.col.decks
        preset = next((c for c in decks.all_config() if c["name"] == "Ankizin"), None) or decks.add_config("Ankizin")

        # fmt: off
        # New cards settings
        preset["new"]["perDay"] = 50

        # Review settings
        preset["rev"]["perDay"] = 9999

        # Learning steps
        preset["new"]["delays"] = [15.0]  # 15 minutes
        preset["lapse"]["delays"] = [15.0]  # 15 minutes for relearning

        # Leech settings
        preset["lapse"]["leechFails"] = 15
        preset["lapse"]["leechAction"] = 1  # 1 = tag only

        # Display order settings
        preset["new"]["order"] = 3  # DeckConfig_Config_NewCardGatherPriority.HIGHEST_POSITION
        preset["newSortOrder"] = 1  # Sortierreihenfolge neuer Karten: Sammelreihenfolge (und Sammelreihenfolge ist typischerweise "Stapel")
        preset["newGatherPriority"] = 2  # ascending
        preset["reviewOrder"] = 4  # DeckConfig_Config_ReviewCardOrder.INTERVALS_DESCENDING
        preset["newMix"] = 1  # Reihenfolge Neu/Wiederholung: Nach Wiederholungen anzeigen

        # Sibling settings
        preset["new"]["bury"] = True  # Bury new siblings
        preset["rev"]["bury"] = True  # Bury review siblings
        preset["buryInterdayLearning"] = True  # Bury interday learning cards

        preset["rev"]["maxIvl"] = 180  # 180 days
        # fmt: on

        decks.update_config(preset)
        for did in dids:
            decks.set_config_id_for_deck_dict(decks.get(did), preset["id"])

    def suspend_cards_from_deck(self, cids=[], all=False):
        # Get the deck object
        if all:
            sus_cids = mw.col.find_cards("tag:#Ankizin_v*")
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

    def handle_first_time_options_op(self):
        CollectionOp(
            parent=mw, op=lambda _: self.handle_first_time_options()
        ).success(AnkizinHelper.on_success).run_in_background()

    def handle_update_options(self):
        if self.suspend_new_cards:
            cids = self.find_new_cards_from_update()
            self.suspend_cards_from_deck(cids, all=False)
        if self.delete_outdated_cards:
            self.delete_marked_cards()

        return OpChanges()

    def handle_update_options_op(self):
        CollectionOp(
            parent=mw, op=lambda _: self.handle_update_options()
        ).success(AnkizinHelper.on_success).run_in_background()

    @staticmethod
    def on_success(out: OpChanges) -> None:
        AnkizinHelper.general_housekeeping()  # always run this

    @staticmethod
    def _after_backup(fut, next_step):
        fut.result()  # raises if the backup failed, so nothing is changed without one
        next_step()

    def run_first_time_setup(self):
        # Check if Ankizin is installed
        if not check_ankizin_installation():
            return

        dialog = FirstSetupConfigDialog(mw, self)
        dialog.setFixedSize(dialog.sizeHint())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            mw.taskman.with_progress(
                mw.create_backup_now,
                on_done=lambda fut: self._after_backup(fut, self.handle_first_time_options_op),
                label="Erstelle Backup...",
                immediate=True,
            )

    def find_new_cards_from_update(self):
        collection = mw.col
        # the Ankizin source is a version number (old), Ankihub or AnkiCollab
        version_pattern = re.compile(r"#Ankizin_v(\d+|Ankihub|AnkiCollab)::§NEW_CARDS::v(\d+)")

        # Group the NEW_CARDS versions by Ankizin source
        version_groups = {}
        for tag in collection.tags.all():
            if match := version_pattern.match(tag):
                version_groups.setdefault(match.group(1), []).append(int(match.group(2)))

        if not version_groups:
            return []

        # Latest source: AnkiCollab, then Ankihub, then the highest version number
        latest_ankizin = max(
            version_groups, key=lambda v: (v == "AnkiCollab", v == "Ankihub", int(v) if v.isdigit() else 0)
        )
        # Find latest NEW_CARDS version within that source
        latest_cards = max(version_groups[latest_ankizin])

        target_tag = f"#Ankizin_v{latest_ankizin}::§NEW_CARDS::v{latest_cards}"
        print(f"Target tag: {target_tag}")
        return collection.find_cards(f"tag:{target_tag}")

    def run_ankizin_update_setup(self):
        # Check if Ankizin is installed
        if not check_ankizin_installation():
            return

        # Ask user what they wanna  do
        dialog = UpdateConfigDialog(mw, self)
        dialog.setFixedSize(dialog.sizeHint())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            mw.taskman.with_progress(
                mw.create_backup_now,
                on_done=lambda fut: self._after_backup(fut, self.handle_update_options_op),
                label="Erstelle Backup...",
                immediate=True,
            )
