import os
import tempfile
import unittest

from anki.collection import Collection
from anki.errors import InvalidInput

from src.projekt_anki_notetypes.butler import hooks, lernplan_decks

MANY = 100  # Anki keeps 30 undo steps (UNDO_LIMIT in rslib/src/undo/mod.rs), far fewer than this


class TestUndoMergeWithManyDecks(unittest.TestCase):
    def setUp(self):
        self.col = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
        for i in range(MANY):
            note = self.col.new_note(self.col.models.by_name("Basic"))
            note["Front"], note["Back"] = f"card{i}x", "b"
            self.col.add_note(note, self.col.decks.id_for_name("Default"))

    def tearDown(self):
        self.col.close()

    def test_rebuild_filtered_decks(self):
        for i in range(MANY):
            deck = self.col.sched.get_or_create_filtered_deck(deck_id=0)
            deck.name = f"Auswahl {i}"
            deck.config.search_terms[0].search = "deck:Default"
            deck.allow_empty = True
            self.col.sched.add_or_update_filtered_deck(deck)
        before = self.col.undo_status().undo
        result = hooks.rebuild_filtered_decks(self.col, enabled=True, only_ankizin=False)
        self.assertEqual(result.failed, [])
        self.assertEqual(self.col.undo_status().undo, "Auswahlstapel neu aufbauen")
        self.col.undo()  # one single step takes back all rebuilds
        self.assertEqual(self.col.undo_status().undo, before)

    def test_create_filtered_decks(self):
        specs = [(f"Auswahl {i}", f"front:card{i}x", False) for i in range(MANY)]
        result = lernplan_decks.create_filtered_decks(self.col, specs)
        self.assertEqual(result.failed, [])
        self.assertEqual(result.skipped, [])
        self.assertEqual(self.col.undo_status().undo, "Auswahlstapel erstellen")
        self.col.undo()  # one single step removes all decks again
        self.assertIsNone(self.col.decks.id_for_name("Auswahl 0"))

    def test_cleanup_of_many_old_decks_is_one_step(self):
        for i in range(MANY):  # empty "!VORHERIGE LERNTAGE::..." decks, removed one at a time
            self.col.decks.id(f"{lernplan_decks.PREVIOUS_PARENT}::Tag {i}")
        before = {d.name for d in self.col.decks.all_names_and_ids()}
        specs = [("Free", "front:card0x", False)]
        result = lernplan_decks.create_filtered_decks(self.col, specs, cleanup=True)
        self.assertEqual(result.failed, [])
        self.assertEqual(self.col.undo_status().undo, "Auswahlstapel erstellen")
        self.col.undo()
        self.assertEqual({d.name for d in self.col.decks.all_names_and_ids()}, before)


class TestBrokenDeckDoesNotStopTheOthers(unittest.TestCase):
    def setUp(self):
        self.col = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
        for i in range(2):
            note = self.col.new_note(self.col.models.by_name("Basic"))
            note["Front"], note["Back"] = f"card{i}x", "b"
            self.col.add_note(note, self.col.decks.id_for_name("Default"))

    def tearDown(self):
        self.col.close()

    def test_rebuild_reports_the_broken_deck_and_goes_on(self):
        for name in ("REBUILD broken", "REBUILD fine"):
            deck = self.col.sched.get_or_create_filtered_deck(deck_id=0)
            deck.name, deck.allow_empty = name, True
            deck.config.search_terms[0].search = "deck:Default"
            self.col.sched.add_or_update_filtered_deck(deck)
        real = self.col.sched.rebuild_filtered_deck

        def flaky(deck_id):
            if self.col.decks.name(deck_id) == "REBUILD broken":
                raise InvalidInput("broken search", None, None, None)
            return real(deck_id)

        self.col.sched.rebuild_filtered_deck = flaky
        result = hooks.rebuild_filtered_decks(self.col, enabled=False, only_ankizin=False)
        self.assertEqual([name for name, _ in result.failed], ["REBUILD broken"])

    def test_create_reports_a_name_clash_and_goes_on(self):
        self.col.decks.id("Blocked")  # a normal deck already uses the name
        specs = [("Blocked", "front:card0x", False), ("Free", "front:card1x", False)]
        result = lernplan_decks.create_filtered_decks(self.col, specs)
        self.assertEqual([name for name, _ in result.failed], ["Blocked"])
        self.assertTrue(self.col.decks.id_for_name("Free"))
