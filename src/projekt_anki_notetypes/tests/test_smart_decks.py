"""Unit tests for ankizin.study_hub.smart_decks."""
from __future__ import annotations

from ankizin.study_hub.smart_decks import (
    DailyNewLimitInfo,
    create_smart_filtered_deck,
    dissolve_smart_deck,
    format_daily_limit_notice,
    get_daily_new_limit_info,
    keep_only_high_yield,
    list_smart_decks,
    maintain_smart_decks,
    suspend_matching_cards,
    unsuspend_matching_cards,
    unsuspend_matching_cards_detailed,
)
from ankizin.study_hub.tag_index import build_topic_search
from .conftest import add_ankizin_note


def test_unsuspend_suspend_and_keep_only_high_yield(tmp_col):
    did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id
    _, hy_cids = add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Kardio",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb",
        ],
        suspended=True,
    )
    _, std_cids = add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Kardio"],
        suspended=True,
    )

    search_all = build_topic_search(
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Kardio"],
        yield_preset="all",
    )
    activated, _ = unsuspend_matching_cards(tmp_col, search_all)
    assert activated == 2
    assert all(tmp_col.get_card(c).queue != -1 for c in hy_cids + std_cids)

    # Post-exam trim keeps HY active and suspends Standard
    kept, paused, _ = keep_only_high_yield(tmp_col, search_all)
    assert kept == 1
    assert paused == 1
    assert tmp_col.get_card(hy_cids[0]).queue != -1
    assert tmp_col.get_card(std_cids[0]).queue == -1

    # Suspend remaining active cards
    susp_cnt, _ = suspend_matching_cards(tmp_col, search_all)
    assert susp_cnt == 1
    assert tmp_col.get_card(hy_cids[0]).queue == -1


def test_smart_deck_daily_and_autoclean_lifecycle(tmp_col, monkeypatch):
    home_did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id
    _, c1 = add_ankizin_note(
        tmp_col,
        home_did,
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Pneumo"],
        suspended=True,
    )
    _, c2 = add_ankizin_note(
        tmp_col,
        home_did,
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Nephro"],
        suspended=True,
    )

    conf = {"smart_decks": {}}
    search_pneumo = build_topic_search(
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Pneumo"],
        yield_preset="all",
    )
    search_nephro = build_topic_search(
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Nephro"],
        yield_preset="all",
    )

    # 1. Create daily Smart Deck
    res_daily = create_smart_filtered_deck(
        tmp_col, conf, "Pneumonie", search_pneumo, lifecycle="daily"
    )
    assert res_daily.created is True
    assert res_daily.card_count == 1
    assert res_daily.unsuspended_count == 1

    # 2. Create auto_clean Smart Deck
    res_auto = create_smart_filtered_deck(
        tmp_col, conf, "Nephrologie", search_nephro, lifecycle="auto_clean"
    )
    assert res_auto.created is True
    assert res_auto.card_count == 1

    def forbid_find_cards(*_a, **_kw):
        raise AssertionError("list_smart_decks must never call col.find_cards!")

    monkeypatch.setattr(tmp_col, "find_cards", forbid_find_cards)
    listed = list_smart_decks(tmp_col, conf)
    assert len(listed) == 2
    assert listed[0].remaining_cards >= 0
    monkeypatch.undo()

    # Simulate finishing the auto_clean deck (cards return to home deck -> 0 left inside filtered deck)
    tmp_col.sched.empty_filtered_deck(res_auto.deck_id)
    assert tmp_col.db.scalar("SELECT count() FROM cards WHERE did = ?", res_auto.deck_id) == 0

    maint = maintain_smart_decks(tmp_col, conf, rebuild_daily=True)
    assert res_auto.deck_name in maint.auto_cleaned
    assert res_daily.deck_name in maint.rebuilt
    assert not tmp_col.decks.get(res_auto.deck_id, default=False)
    # Home card must NEVER be deleted
    assert tmp_col.get_card(c2[0]).did == home_did

    # 3. Dissolve daily Smart Deck safely; refuse dissolving normal home deck
    assert dissolve_smart_deck(tmp_col, conf, home_did) is False
    assert dissolve_smart_deck(tmp_col, conf, res_daily.deck_id) is True
    assert not tmp_col.decks.get(res_daily.deck_id, default=False)
    assert tmp_col.get_card(c1[0]).did == home_did


def test_daily_new_limit_info_and_notice(tmp_col):
    parent_did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id
    child_did = tmp_col.decks.add_normal_deck_with_name("Ankizin::Klinik").id

    # Parent preset new.perDay = 40, child preset new.perDay = 60 -> effective parent cap = 40
    p_cfg_id = tmp_col.decks.add_config_returning_id("Ankizin Parent")
    p_cfg = tmp_col.decks.get_config(p_cfg_id)
    p_cfg["new"]["perDay"] = 40
    tmp_col.decks.save(p_cfg)
    tmp_col.decks.set_config_id_for_deck_dict(tmp_col.decks.get(parent_did), p_cfg_id)

    c_cfg_id = tmp_col.decks.add_config_returning_id("Ankizin Child")
    c_cfg = tmp_col.decks.get_config(c_cfg_id)
    c_cfg["new"]["perDay"] = 60
    tmp_col.decks.save(c_cfg)
    tmp_col.decks.set_config_id_for_deck_dict(tmp_col.decks.get(child_did), c_cfg_id)

    all_cids: list[int] = []
    for _ in range(3):
        _, cids = add_ankizin_note(
            tmp_col,
            child_did,
            ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere::Pneumonie"],
            suspended=True,
        )
        all_cids.extend(cids)

    search = build_topic_search(
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere::Pneumonie"],
        yield_preset="all",
    )
    unsusp_cids, _ = unsuspend_matching_cards_detailed(tmp_col, search)
    assert len(unsusp_cids) == 3

    info = get_daily_new_limit_info(tmp_col, unsusp_cids)
    assert info.daily_limit == 40
    assert info.total_active_new == 3
    assert info.deck_name == "Ankizin"

    # Notice triggered when activating 100 cards with limit 40 -> explains 40 today & 60 later
    notice_big = format_daily_limit_notice(100, info)
    assert "40" in notice_big and "60" in notice_big

    # Notice suppressed when within daily limit
    assert format_daily_limit_notice(10, DailyNewLimitInfo(40, 10, "Ankizin")) == ""
