"""Unit tests for ankizin.setup.engine."""
from __future__ import annotations

from ankizin.onboarding import engine
from .conftest import add_ankizin_note


def test_apply_recommended_settings_isolates_ankizin_decks(tmp_col):
    ankizin_did = tmp_col.decks.add_normal_deck_with_name("Ankizin::Klinik").id
    other_did = tmp_col.decks.add_normal_deck_with_name("Meine eigenen Karten").id

    add_ankizin_note(tmp_col, ankizin_did, ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::Kardio"])
    add_ankizin_note(tmp_col, other_did, ["privat"])

    res = engine.apply_recommended_ankizin_settings(tmp_col, new_per_day=35)
    assert res["decks_assigned"] >= 1
    assert res["new_per_day"] == 35
    assert res["max_ivl"] == 3600
    assert tmp_col.get_config("fsrs") is True
    assert tmp_col.get_config("newSpread") == 1

    ankizin_deck = tmp_col.decks.get(ankizin_did)
    other_deck = tmp_col.decks.get(other_did)
    preset = tmp_col.decks.get_config(ankizin_deck["conf"])
    assert preset["name"] == "Ankizin"
    assert preset["new"]["perDay"] == 35
    assert preset["rev"]["perDay"] == 9999
    assert preset["rev"]["maxIvl"] == 3600
    assert preset["new"]["delays"] == [15.0]
    assert preset["lapse"]["leechAction"] == 1
    assert preset["newMix"] == 1
    assert other_deck["conf"] == 1  # unrelated deck untouched


def test_suspend_only_new_preserves_reviewed(tmp_col):
    did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id
    _, new_cids = add_ankizin_note(tmp_col, did, ["#Ankizin_vAnkiCollab::Test"], reviewed=False)
    _, rev_cids = add_ankizin_note(tmp_col, did, ["#Ankizin_vAnkiCollab::Test"], reviewed=True)

    cnt = engine.suspend_ankizin_cards(tmp_col, only_new=True)
    assert cnt == len(new_cids)
    assert all(tmp_col.get_card(c).queue == -1 for c in new_cids)
    assert all(tmp_col.get_card(c).queue != -1 for c in rev_cids)


def test_delete_marked_notes_distinguishes_unlearned_vs_reviewed(tmp_col):
    did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id
    unlearned_note, _ = add_ankizin_note(
        tmp_col, did, ["#Ankizin_vAnkiCollab::!DELETE::update"], reviewed=False
    )
    reviewed_note, _ = add_ankizin_note(
        tmp_col, did, ["#Ankizin_v4::!DELETE::duplicate"], reviewed=True
    )
    keep_note, _ = add_ankizin_note(
        tmp_col, did, ["#Ankizin_vAnkiCollab::Kardio"], reviewed=False
    )

    unlearned, reviewed = engine.find_delete_marked_notes(tmp_col)
    assert unlearned == [unlearned_note.id]
    assert reviewed == [reviewed_note.id]

    deleted, skipped = engine.delete_marked_notes(tmp_col, include_reviewed=False)
    assert deleted == 1
    assert skipped == 1
    assert tmp_col.db.scalar("SELECT count() FROM notes WHERE id = ?", unlearned_note.id) == 0
    assert tmp_col.db.scalar("SELECT count() FROM notes WHERE id = ?", reviewed_note.id) == 1
    assert tmp_col.db.scalar("SELECT count() FROM notes WHERE id = ?", keep_note.id) == 1

    deleted2, skipped2 = engine.delete_marked_notes(tmp_col, include_reviewed=True)
    assert deleted2 == 1
    assert skipped2 == 0
    assert tmp_col.db.scalar("SELECT count() FROM notes WHERE id = ?", reviewed_note.id) == 0


def test_set_deck_aside_and_empty_filtered(tmp_col):
    did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id
    add_ankizin_note(tmp_col, did, ["#Ankizin_v5::Innere"])

    renamed1 = engine.set_deck_aside(tmp_col, did)
    assert renamed1 == "Ankizin_alt"
    did2 = tmp_col.decks.add_normal_deck_with_name("Ankizin").id
    renamed2 = engine.set_deck_aside(tmp_col, did2)
    assert renamed2 == "Ankizin_alt 2"

    # Filtered deck holding an Ankizin card gets emptied safely
    from anki.decks import FilteredDeckConfig

    fdeck = tmp_col.sched.get_or_create_filtered_deck(0)
    fdeck.name = "TempFiltered"
    del fdeck.config.search_terms[:]
    fdeck.config.search_terms.append(FilteredDeckConfig.SearchTerm(search="tag:#Ankizin_v5::Innere", limit=100, order=0))
    tmp_col.sched.add_or_update_filtered_deck(fdeck)
    assert engine.empty_ankizin_filtered_decks(tmp_col) == 1


def test_configure_collection_flags_and_personal_tags(tmp_col):
    did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id
    _, stark_cids = add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb",
            "Semester6::Wichtig",
        ],
    )
    _, leicht_cids = add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::02-leicht_gelb"],
    )
    # Pre-existing user flag (3 = green) must NOT be overwritten
    _, preflagged = add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb"],
    )
    tmp_col.set_user_flag_for_cards(3, preflagged)
    add_ankizin_note(tmp_col, did, ["#Ankizin_vAnkiCollab::!DELETE::update"])

    personal = engine.detect_personal_tags_on_ankizin(tmp_col)
    assert personal == ["Semester6::Wichtig"]

    summary = engine.configure_ankizin_collection(
        tmp_col,
        {
            "suspend_cards": True,
            "suspend_only_new": True,
            "apply_settings": True,
            "new_per_day": 25,
            "delete_marked": True,
            "flag_high_yield": True,
        },
    )
    assert summary["deleted"] == 1
    assert summary["suspended"] == 3
    assert summary["flagged_stark"] == 1
    assert summary["flagged_leicht"] == 1
    assert tmp_col.get_card(stark_cids[0]).flags & 7 == 1
    assert tmp_col.get_card(leicht_cids[0]).flags & 7 == 2
    assert tmp_col.get_card(preflagged[0]).flags & 7 == 3


def test_detect_setup_state_scenarios(tmp_col):
    # 1. Brand new collection -> guided installation
    snap = engine.detect_setup_state(
        col=tmp_col,
        collab_override={"status": "missing", "logged_in": False, "subscribed": False, "installed_did": 0},
        ankihub_override=[],
        ankiweb_override=False,
        state_override={},
    )
    assert snap["scenario"] == "new"

    # 2. Incomplete subscription download (no Ankizin tags yet)
    snap_inc = engine.detect_setup_state(
        col=tmp_col,
        collab_override={"status": "loaded", "logged_in": True, "subscribed": True, "installed_did": 0},
        ankihub_override=[],
        ankiweb_override=False,
        state_override={},
    )
    assert snap_inc["scenario"] == "incomplete"

    # 3. Old .apkg version (#Ankizin_v5 / v4 / v3) -> upgrade to AnkiCollab
    did = tmp_col.decks.add_normal_deck_with_name("Ankizin_v5").id
    add_ankizin_note(tmp_col, did, ["#Ankizin_v5::Kardio", "#Ankizin_v4::Pneumo"])
    snap_apkg = engine.detect_setup_state(
        col=tmp_col,
        collab_override={"status": "missing", "logged_in": False, "subscribed": False, "installed_did": 0},
        ankihub_override=[],
        ankiweb_override=False,
        state_override={},
    )
    assert snap_apkg["scenario"] == "migrate_apkg"
    assert snap_apkg["tag_sources"]["legacy_versions"] == ["v5", "v4"]

    # 4. #Ankizin_vAnkihub tags (even without AnkiHub addon installed) -> migrate to AnkiCollab
    add_ankizin_note(tmp_col, did, ["#Ankizin_vAnkihub::Kardio"])
    snap_ah_tags = engine.detect_setup_state(
        col=tmp_col,
        collab_override={"status": "missing", "logged_in": False, "subscribed": False, "installed_did": 0},
        ankihub_override=[],
        ankiweb_override=True,
        state_override={},
    )
    assert snap_ah_tags["scenario"] == "migrate_ankihub"

    # 5. Already on #Ankizin_vAnkiCollab -> ready (no installation guidance needed)
    add_ankizin_note(tmp_col, did, ["#Ankizin_vAnkiCollab::Kardio"])
    snap_ready = engine.detect_setup_state(
        col=tmp_col,
        collab_override={"status": "loaded", "logged_in": True, "subscribed": True, "installed_did": did},
        ankihub_override=[],
        ankiweb_override=True,
        state_override={},
    )
    assert snap_ready["scenario"] == "ready"

    # 6. Dual collision (#Ankizin_vAnkiCollab + active AnkiHub addon subscription) -> dual
    snap_dual = engine.detect_setup_state(
        col=tmp_col,
        collab_override={"status": "loaded", "logged_in": True, "subscribed": True, "installed_did": did},
        ankihub_override=[{"uuid": "abc", "name": "Ankizin", "anki_did": did}],
        ankiweb_override=True,
        state_override={},
    )
    assert snap_dual["scenario"] == "dual"
