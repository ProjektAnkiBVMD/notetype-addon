from aqt import mw
from aqt.qt import *
import re
from aqt.operations import CollectionOp
from anki.collection import OpChanges

from .utils import async_general_housekeeping, check_ankizin_installation
from .gui import FirstSetupConfigDialog, UpdateConfigDialog
from ..onboarding import engine as _setup_engine


class AnkizinHelper:

    def __init__(self):
        self.DELETE_TAG_PATTERN = _setup_engine.DELETE_TAG_REGEX

        self.delete_outdated_cards = True
        self.update_deck_config = False
        self.suspend_all_cards = True
        self.suspend_new_cards = True

    def delete_marked_cards(self):
        deleted, _ = _setup_engine.delete_marked_notes(mw.col, include_reviewed=True)
        print(f"Deleting {deleted} notes")

    @staticmethod
    def general_housekeeping():
        async_general_housekeeping()

    def setup_collection_config(self):
        _setup_engine.apply_recommended_ankizin_settings(mw.col, new_per_day=50, max_ivl=3600)

    def optimize_settings(self):
        _setup_engine.apply_recommended_ankizin_settings(mw.col, new_per_day=50, max_ivl=3600)

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
