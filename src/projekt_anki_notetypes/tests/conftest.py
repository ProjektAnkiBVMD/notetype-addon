"""Pytest fixtures for Ankizin v2 overhaul tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import aqt
import pytest
from anki.collection import Collection

# Ensure `import ankizin...` resolves without executing Anki startup hooks.
aqt.mw = None

ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def tmp_col(tmp_path):
    """Real temporary Anki Collection closed cleanly after each test."""
    col_path = tmp_path / "collection.anki2"
    col = Collection(str(col_path))
    try:
        yield col
    finally:
        col.close()


def add_ankizin_note(
    col: Collection,
    deck_id: int,
    tags: list[str],
    text: str = "Typischer Erreger der Pneumonie ist {{c1::Streptococcus pneumoniae}}.",
    extra: str = "Zusatzinfo",
    suspended: bool = False,
    reviewed: bool = False,
):
    """Create a realistic Cloze note with given tags and card state."""
    model = col.models.by_name("Cloze") or col.models.by_name("Lückentext")
    note = col.new_note(model)
    note.fields[0] = text
    if len(note.fields) > 1:
        note.fields[1] = extra
    note.tags = list(tags)
    col.add_note(note, deck_id)

    cids = col.card_ids_of_note(note.id)
    if reviewed:
        for cid in cids:
            card = col.get_card(cid)
            card.type = 2
            card.queue = 2
            card.reps = 4
            card.ivl = 12
            col.update_card(card)
    if suspended:
        col.sched.suspend_cards(cids)
    return note, cids


class DummyAddonManager:
    def __init__(self, initial=None):
        self._configs = dict(initial or {})
        self._addons = {}

    def getConfig(self, name):
        return dict(self._configs.get(name, {}))

    def writeConfig(self, name, data):
        self._configs[name] = dict(data)

    def allAddons(self):
        return list(self._addons.keys())

    def isEnabled(self, addon_id):
        return bool(self._addons.get(addon_id, False))


class DummyProgress:
    def busy(self):
        return False

    def start(self, *a, **kw):
        pass

    def finish(self):
        pass


class DummyTaskman:
    def run_on_main(self, fn):
        fn()


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from aqt.qt import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_mw(tmp_col, monkeypatch):
    """Attach a realistic headless `mw` stub backed by a real Collection."""
    from ankizin.constants import ADDON_DIR_NAME
    import ankizin.onboarding.engine as engine_mod
    import ankizin.onboarding.maintenance as maint_mod
    import ankizin.onboarding.wizard as wizard_mod
    import ankizin.study_hub.dialog as hub_mod
    import ankizin.home.dashboard as home_mod

    pm = SimpleNamespace(
        profile={},
        save=lambda: None,
        sync_auth=lambda: None,
        auto_syncing_enabled=lambda: False,
        media_syncing_enabled=lambda: False,
    )
    addon_mgr = DummyAddonManager(
        {
            ADDON_DIR_NAME: {
                "autoRebuildDecksOnStartup": True,
                "autoRebuildOnlyAnkizinDecks": False,
                "auto_delete_marked_cards": "unlearned",
                "auto_sync_ankicollab_on_startup": True,
                "show_home_quickbar": True,
                "smart_decks": {},
                "study_hub": {
                    "last_category": "amboss",
                    "last_yield": "high_yield",
                    "last_mode": "unsuspend",
                    "exclude_zahni": True,
                },
            }
        }
    )
    fake_mw = SimpleNamespace(
        col=tmp_col,
        pm=pm,
        addonManager=addon_mgr,
        progress=DummyProgress(),
        taskman=DummyTaskman(),
        state="deckBrowser",
        deckBrowser=SimpleNamespace(refresh=lambda: None),
        reset=lambda: None,
        moveToState=lambda *_a, **_kw: None,
        create_backup_now=lambda: True,
        close=lambda: None,
    )

    monkeypatch.setattr(aqt, "mw", fake_mw, raising=False)
    for mod in (maint_mod, wizard_mod, hub_mod, home_mod):
        monkeypatch.setattr(mod, "mw", fake_mw, raising=False)
    monkeypatch.setattr(engine_mod, "_mw", lambda: fake_mw)
    return fake_mw
