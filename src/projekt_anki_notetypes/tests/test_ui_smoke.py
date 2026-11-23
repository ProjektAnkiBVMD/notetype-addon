"""Headless Qt UI smoke tests (macOS screen bounds, zero-freeze hub, mnemonics, home bar)."""
from __future__ import annotations

from aqt.qt import QScrollArea, QSplitter, Qt

from ankizin.constants import ADDON_DIR_NAME
from ankizin.home.dashboard import on_webview_js_message, render_home_banner_html
from ankizin.onboarding.maintenance import MaintenanceDialog
from ankizin.onboarding.wizard import AnkizinSetupWizard
from ankizin.study_hub import dialog as hub_dialog_mod
from ankizin.study_hub.dialog import AnkizinStudyHubDialog
from ankizin.study_hub.smart_decks import DailyNewLimitInfo, create_smart_filtered_deck
from ankizin.study_hub.tag_index import build_tag_index, build_topic_search, refresh_card_states
from ankizin.ui.styles import ANKIZIN_STYLE
from .conftest import add_ankizin_note


def test_setup_wizard_pages_mnemonics_and_mac_bounds(qapp, mock_mw, tmp_col):
    info_new = {
        "scenario": "new",
        "settings": {"deck_key": "decke-schaufeln-reiche"},
        "deck_key": "decke-schaufeln-reiche",
        "collab_status": "missing",
        "collab_logged_in": False,
        "subscribed": False,
        "installed_did": 0,
        "collab_settings": {},
        "ankihub_decks": [],
        "tag_sources": {"has_collab": False, "has_ankihub": False, "has_legacy_apkg": False, "legacy_versions": []},
        "has_content": False,
        "old_decks": [],
        "configured": False,
        "preset_ready": False,
        "ankiweb": False,
    }
    wiz = AnkizinSetupWizard(info_override=info_new)
    assert wiz.current == "welcome"
    assert wiz.width() <= 1280 and wiz.height() <= 800
    # Verify StepRail renders "Fertig & loslernen" (no double &&)
    finish_rail_html = wiz._rail._labels["finish"].text()
    assert "Fertig &amp; loslernen" in finish_rail_html
    assert "&amp;&amp;" not in finish_rail_html

    wiz.show()
    wiz.go("install")
    assert wiz.current == "install"
    wiz.go("account")
    assert wiz.current == "account"
    wiz.go("configure")
    qapp.processEvents()
    assert wiz.current == "configure"
    assert wiz._rail.width() <= 180
    sa = wiz.findChild(QScrollArea)
    assert sa is not None and sa.widget() is not None
    assert sa.widget().width() <= sa.viewport().width()
    from aqt.qt import QWidget as _QWidget
    for child in sa.widget().findChildren(_QWidget):
        if child.isVisible():
            assert child.width() <= sa.viewport().width()
    assert wiz._suspend_cb.isChecked()
    assert wiz._fsrs_cb.isChecked()
    wiz.close()

    info_ready = dict(
        info_new,
        scenario="ready",
        collab_status="loaded",
        collab_logged_in=True,
        subscribed=True,
        installed_did=1,
        configured=True,
    )
    wiz_ready = AnkizinSetupWizard(info_override=info_ready)
    assert wiz_ready.current == "finish"
    wiz_ready.close()


def test_study_hub_3step_zero_freeze_and_bounds(qapp, mock_mw, tmp_col, monkeypatch):
    did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere::Kardiologie",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb",
        ],
        suspended=True,
    )
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere::Pneumologie",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::02-leicht_gelb",
        ],
        suspended=False,
    )

    # Verify searching inside AMBOSS scopes out Unis and nests Pneumonie subtopics
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere::Pneumologie::Pneumonie::Diagnostik",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::02-leicht_gelb",
        ],
        suspended=True,
    )
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere::Pneumologie::Pneumonie::Therapie",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb",
        ],
        suspended=True,
    )
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#UNIVERSITÄTEN::Uni_Berlin::Block_5::Pneumonie",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb",
        ],
        suspended=True,
    )
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#UNIVERSITÄTEN::Uni_Berlin::Block_5::ExklusivUniThema",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb",
        ],
        suspended=True,
    )

    hub = AnkizinStudyHubDialog()
    assert hub.width() <= 1280 and hub.height() <= 800
    # Full-width top-to-bottom layout: zero QSplitter, zero horizontal scrollbars, zero preview panel,
    # and zero duplicate inline progress runners (CollectionOp supplies the single progress popup)
    assert hub.findChildren(QSplitter) == []
    assert not hasattr(hub, "_preview_scroll")
    assert not hasattr(hub, "_busy_bar_wrap")
    assert not hasattr(hub, "_smart_busy_wrap")
    for sa in hub.findChildren(QScrollArea):
        assert sa.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    # Starts on Step 0 (Thema wählen) with Step 2 button disabled until a topic is picked
    assert hub._main_stack.currentIndex() == 2
    assert hub._step_stack.currentIndex() == 0
    assert not hub._to_step2_btn.isEnabled()
    assert hub._tree.topLevelItemCount() >= 1

    # Selecting/searching/filtering topics MUST NEVER call col.find_cards() on main thread
    def forbid_find_cards(*_a, **_kw):
        raise AssertionError("col.find_cards must not be called during topic selection!")

    monkeypatch.setattr(tmp_col, "find_cards", forbid_find_cards)

    # Converged article-level search for "Pneumonie": clean top-level article row (no parent wrapper,
    # no "+N identische Pfade" clutter), #1 hit bold & auto-selected, subtopics expandable underneath
    hub._search_input.setText("Pneumonie")
    hub._populate_topic_tree()
    assert hub._tree.topLevelItemCount() == 1
    pneu_item = hub._tree.topLevelItem(0)
    assert pneu_item.text(0) == "Pneumonie"
    assert "identische Pfade" not in pneu_item.text(0)
    assert pneu_item.font(0).bold() is True
    assert hub._tree.currentItem() is pneu_item
    assert pneu_item.childCount() == 2
    assert not pneu_item.isExpanded()
    assert hub._tree.rootIsDecorated() is True
    assert not hub._fallback_bar.isVisible()

    # Zero-hit term in AMBOSS offers cross-category fallback without leaving AMBOSS silently
    hub._search_input.setText("ExklusivUniThema")
    hub._populate_topic_tree()
    assert hub._tree.topLevelItemCount() == 0
    assert not hub._fallback_bar.isHidden()
    assert "(1)" in hub._fallback_btn.text()

    # Clearing search restores the full nested category tree (Innere -> Kardiologie / Pneumologie)
    hub._search_input.setText("")
    hub._populate_topic_tree()
    assert hub._tree.topLevelItemCount() == 1
    assert hub._tree.topLevelItem(0).text(0) == "Innere"
    assert hub._tree.topLevelItem(0).childCount() == 2

    # Zahni toggle is completely gone; TOP-100 filter & sort live in Step 1 topic panel
    assert not hasattr(hub, "_zahni_cb")
    assert hub._tree.objectName() == "ankizin_topic_tree"
    assert "QTreeWidget#ankizin_topic_tree" in ANKIZIN_STYLE
    assert "selection-background-color: transparent" in ANKIZIN_STYLE
    assert "border-radius: 0px" in ANKIZIN_STYLE
    assert hub._search_input.parentWidget() is hub._top100_cb.parentWidget()

    # Step 1 card counts always stay fixed on Normal + High + Highest Yield ("standard"),
    # regardless of which Yield option was last selected in Step 2
    hub._search_input.setText("Pneumonie")
    hub._populate_topic_tree()
    count_before = hub._tree.topLevelItem(0).text(1)
    hub._yield_radios["stark"].setChecked(True)
    assert hub._tree.topLevelItem(0).text(1) == count_before
    hub._yield_radios["all"].setChecked(True)
    assert hub._tree.topLevelItem(0).text(1) == count_before
    hub._yield_radios["stark"].setChecked(True)

    hub._search_input.setText("Kardiologie")
    hub._populate_topic_tree()
    assert hub._tree.topLevelItemCount() == 1
    assert hub._tree.topLevelItem(0).text(0) == "Kardiologie"
    assert hub._tree.rootIsDecorated() is False

    # Sort combo works in RAM without DB queries
    hub._sort_combo.setCurrentIndex(hub._sort_combo.findData("size"))
    hub._sort_combo.setCurrentIndex(hub._sort_combo.findData("progress"))
    hub._sort_combo.setCurrentIndex(hub._sort_combo.findData("alpha"))

    # TOP-100 filter updates tree cleanly in RAM without DB queries
    hub._top100_cb.setChecked(True)
    assert hub._tree.topLevelItemCount() == 0
    hub._top100_cb.setChecked(False)
    assert hub._tree.topLevelItemCount() == 1

    kardio_item = hub._tree.topLevelItem(0)
    hub._tree.setCurrentItem(kardio_item)
    assert hub._to_step2_btn.isEnabled()

    # Step 2 (Yield + learning stages)
    hub._go_to_step(1)
    assert hub._step_stack.currentIndex() == 1
    assert "Kardiologie" in hub._sel_title.text()
    assert "neu" in hub._sel_stages_lbl.text()
    assert hub._yield_count_badges["stark"].text() == "1 Karten"

    # Step 3 (Freischalten)
    hub._go_to_step(2)
    assert hub._step_stack.currentIndex() == 2
    assert "Kardiologie" in hub._step3_recap_lbl.text()
    assert hub._primary_btn.isEnabled()

    monkeypatch.undo()

    # Fast refresh_card_states updates active topic + detects Nachzügler cleanly
    for _ in range(9):
        add_ankizin_note(
            tmp_col,
            did,
            [
                "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Neurologie",
                "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb",
            ],
            suspended=False,
        )
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Neurologie",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb",
        ],
        suspended=True,
    )
    rebuilt = build_tag_index(tmp_col)
    fast_refreshed = refresh_card_states(tmp_col, rebuilt)
    monkeypatch.setattr(
        hub_dialog_mod,
        "build_tag_index",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("build_tag_index must not run on main thread!")),
    )
    hub._apply_rebuilt_index(
        fast_refreshed, DailyNewLimitInfo(daily_limit=0, total_active_new=0, deck_name="Ankizin"), repopulate_tree=True
    )
    assert hub._limit_hint_lbl.isHidden()
    assert not hub._straggler_banner.isHidden()
    assert len(hub._straggler_cids) == 1

    # When suspended cards exceed daily limit, Step 3 explains the limit upfront
    hub._apply_rebuilt_index(fast_refreshed, DailyNewLimitInfo(daily_limit=1, total_active_new=1, deck_name="Ankizin"))
    assert not hub._limit_hint_lbl.isHidden()
    assert "Tageslimit" in hub._limit_hint_lbl.text()

    # Render tree cleanly offscreen with _AnkizinTopicTree custom drawRow/drawBranches
    pixmap = hub._tree.grab()
    assert pixmap.width() > 0 and pixmap.height() > 0

    monkeypatch.undo()

    # Smart decks view accessible via header button and MUST NEVER call col.find_cards()
    conf = mock_mw.addonManager.getConfig(ADDON_DIR_NAME)
    search_k = build_topic_search(
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere::Kardiologie"],
        yield_preset="all",
    )
    res = create_smart_filtered_deck(tmp_col, conf, "Kardiologie", search_k, lifecycle="daily")
    assert res.created
    mock_mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)

    monkeypatch.setattr(tmp_col, "find_cards", forbid_find_cards)
    hub._toggle_smart_page()
    assert hub._main_stack.currentIndex() == 3
    hub._toggle_smart_page()
    assert hub._main_stack.currentIndex() == 2
    hub.close()


def test_study_hub_async_skeleton_open(qapp, mock_mw, tmp_col, monkeypatch):
    from concurrent.futures import Future

    did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere::Kardiologie",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb",
        ],
        suspended=True,
    )

    queued: list[tuple] = []
    monkeypatch.setattr(mock_mw, "_increase_background_ops", lambda: None, raising=False)
    monkeypatch.setattr(mock_mw, "_decrease_background_ops", lambda: None, raising=False)
    monkeypatch.setattr(
        mock_mw.taskman,
        "run_in_background",
        lambda op, on_done, **_kw: queued.append((op, on_done)),
        raising=False,
    )

    orig_build = hub_dialog_mod.build_tag_index
    calls: list[int] = []

    def tracked_build(col):
        calls.append(1)
        return orig_build(col)

    monkeypatch.setattr(hub_dialog_mod, "build_tag_index", tracked_build)

    # Dialog constructs immediately without running build_tag_index and shows Skeleton Loading (index 0)
    hub = AnkizinStudyHubDialog()
    assert calls == []
    assert len(queued) == 1
    assert hub._main_stack.currentIndex() == 0

    # Complete the queued QueryOp -> switches cleanly into 3-step flow (index 2)
    op, on_done = queued[0]
    fut: Future = Future()
    fut.set_result(op())
    on_done(fut)

    assert len(calls) == 1
    assert hub._main_stack.currentIndex() == 2
    assert hub._tree.topLevelItemCount() >= 1
    hub.close()


def test_maintenance_dialog_and_home_banner(qapp, mock_mw, tmp_col):
    dlg = MaintenanceDialog()
    assert dlg.width() <= 1280 and dlg.height() <= 800
    dlg.close()

    html_new = render_home_banner_html({"scenario": "new"}, {}, {}, 0)
    assert "ankizin:open_wizard" in html_new

    html_ready = render_home_banner_html(
        {"scenario": "ready", "collab_logged_in": True},
        {},
        {"show_home_quickbar": True},
        pending_deletes=2,
    )
    assert "ankizin:open_hub" in html_ready
    assert "!DELETE prüfen (2)" in html_ready

    assert on_webview_js_message((False, None), "other:cmd", None) == (False, None)
    assert on_webview_js_message((False, None), "ankizin:dismiss_banner", None) == (True, None)
    assert mock_mw.pm.profile["ankizin_setup_state"]["dismissed_home_banner"] is True
