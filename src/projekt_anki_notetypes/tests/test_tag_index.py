"""Unit tests for ankizin.study_hub.tag_index."""
from __future__ import annotations

from ankizin.study_hub.tag_index import (
    build_tag_index,
    build_topic_search,
    fetch_topic_preview,
    find_stragglers,
    format_topic_label,
    refresh_card_states,
)
from .conftest import add_ankizin_note


def test_format_topic_label():
    assert format_topic_label("#Bibliothek-Klinik") == "Bibliothek-Klinik"
    assert format_topic_label("01_Innere_Medizin") == "Innere Medizin"
    assert format_topic_label("M2_Lerntag_005_Kardiologie") == "Tag 005 – Kardiologie"


def test_tag_index_counts_dedup_and_yield_presets(tmp_col):
    did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id

    # Note 1: stark gelb, in TWO sibling subtopics under Kardiologie (must NOT double count Kardiologie!)
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::01_Innere_Medizin::Kardiologie::Herzinsuffizienz",
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::01_Innere_Medizin::Kardiologie::KHK",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-stark_gelb_(highest_yield)_M2",
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::M2-TOP100-Themen::Herzinsuffizienz",
        ],
        suspended=True,
    )
    # Note 2: leicht gelb (active)
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::01_Innere_Medizin::Kardiologie::Herzinsuffizienz",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::02-leicht_gelb_(high_yield)_M2",
        ],
        suspended=False,
    )
    # Note 3: untagged yield (Standard), Zahni-only -> hidden when exclude_zahni=True
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::01_Innere_Medizin::Kardiologie::Herzinsuffizienz",
            "#Ankizin_vAnkiCollab::Zahni-Fokus",
        ],
        suspended=True,
    )
    # Note 4: low yield
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::M2-100-Tage-Lernplan::M2_Lerntag_001_Kardiologie",
            "#Ankizin_vAnkiCollab::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::04-verzichtbar_(low_yield)_M2",
        ],
        suspended=True,
    )
    # Note 5: !DELETE note (must never show up in Study Hub)
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::01_Innere_Medizin::Kardiologie::Herzinsuffizienz",
            "#Ankizin_vAnkiCollab::!DELETE::update",
        ],
        suspended=True,
    )

    # Notes in dropped categories (pharma / meditricks / other) must not create category tabs
    add_ankizin_note(
        tmp_col,
        did,
        [
            "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#IMPP-Arzneistoffliste::Betablocker",
            "#Ankizin_vAnkiCollab::#MEDITRICKS::Kardiologie",
        ],
        suspended=True,
    )

    idx = build_tag_index(tmp_col)
    cats = {k for k, _, _ in idx.available_categories()}
    assert cats == {"amboss", "lernplan", "top100"}

    innere = idx.roots["amboss"][0]
    assert innere.display_name == "Innere Medizin"
    kardio = innere.children[0]
    assert kardio.display_name == "Kardiologie"

    # Deduplication: Kardiologie has 2 non-Zahni, non-DELETE notes (Note 1 + Note 2)
    st_all = kardio.stats(yield_preset="all", exclude_zahni=True)
    assert st_all.total == 2
    assert st_all.active == 1
    assert st_all.suspended == 1

    # Pure RAM combined_stats & yield_breakdown across multiple nodes
    lerntag1 = idx.roots["lernplan"][0]
    breakdown = idx.yield_breakdown([kardio, lerntag1], exclude_zahni=True)
    assert breakdown["stark"].total == 1
    assert breakdown["high_yield"].total == 2
    assert breakdown["standard"].total == 2
    assert breakdown["all"].total == 3

    # Including Zahni adds Note 3 -> total 3
    st_zahni = kardio.stats(yield_preset="all", exclude_zahni=False)
    assert st_zahni.total == 3

    # Stark only -> only Note 1
    st_stark = kardio.stats(yield_preset="stark", exclude_zahni=True)
    assert st_stark.total == 1
    assert st_stark.suspended == 1

    # TOP-100 filter -> only Note 1
    st_top100 = kardio.stats(yield_preset="all", top100_only=True, exclude_zahni=True)
    assert st_top100.total == 1

    # Search
    hits = idx.search("Herzinsuffizienz", yield_preset="high_yield")
    assert hits and hits[0].display_name == "Herzinsuffizienz"

    # Preview prettifies cloze syntax
    previews = fetch_topic_preview(tmp_col, [kardio.full_tag], yield_preset="high_yield")
    assert len(previews) == 2
    assert "{{c1::" not in previews[0].snippet
    assert "[Streptococcus pneumoniae]" in previews[0].snippet

    # Search query excludes !DELETE and matches exact yield cards in Anki
    q = build_topic_search([kardio.full_tag], yield_preset="stark", exclude_zahni=True)
    assert len(tmp_col.find_cards(q)) == 1


def test_hierarchical_scoped_search_pneumonie_and_lerntag(tmp_col):
    did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id

    # AMBOSS: Pneumonie with subtopics Pathophysiologie, Diagnostik, Therapie + sibling Atypische_Pneumonie
    for sub in ("Pathophysiologie", "Diagnostik", "Therapie"):
        add_ankizin_note(
            tmp_col,
            did,
            [f"#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere_Medizin::Pneumologie::Pneumonie::{sub}"],
            suspended=True,
        )
    add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere_Medizin::Pneumologie::Atypische_Pneumonie"],
        suspended=True,
    )

    # Universities + 100-Tage-Plan also mention Pneumonie
    add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::#UNIVERSITÄTEN::Uni_A::Block_1::Pneumonie"],
        suspended=True,
    )
    add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::#UNIVERSITÄTEN::Uni_B::Semester_6::Pneumonie"],
        suspended=True,
    )
    add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::M2-100-Tage-Lernplan::M2_Lerntag_009_Pneumologie::Pneumonie"],
        suspended=True,
    )

    idx = build_tag_index(tmp_col)

    # Searching "Pneumonie" inside AMBOSS returns ONLY [Pneumonie, Atypische Pneumonie] (exact match first!)
    amboss_hits = idx.search_tree("Pneumonie", category_key="amboss", yield_preset="all")
    assert [n.display_name for n in amboss_hits] == ["Pneumonie", "Atypische Pneumonie"]
    # Subtopics stay nested inside Pneumonie instead of flooding flat results
    assert [ch.display_name for ch in amboss_hits[0].children] == [
        "Diagnostik",
        "Pathophysiologie",
        "Therapie",
    ]

    # Specific multi-token query descends into matching child
    therapie_hits = idx.search_tree("Pneumonie Therapie", category_key="amboss", yield_preset="all")
    assert [n.display_name for n in therapie_hits] == ["Therapie"]

    # Leading-zero normalization matches "Tag 9" -> "Tag 009 – Pneumologie"
    lp_hits = idx.search_tree("Tag 9", category_key="lernplan", yield_preset="all")
    assert len(lp_hits) == 1
    assert lp_hits[0].display_name == "Tag 009 – Pneumologie"


def test_nested_search_o1_convergence_refresh_and_stragglers(tmp_col):
    did = tmp_col.decks.add_normal_deck_with_name("Ankizin").id

    # Shared notes tagged identically across AMBOSS Pneumologie, Infektiologie,
    # cross-cutting Behandlungsanlässe › Husten, 100-Tage-Plan, and Uni
    shared_cids: list[int] = []
    for sub in ("Diagnostik", "Therapie"):
        _, cids = add_ankizin_note(
            tmp_col,
            did,
            [
                f"#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere::Pneumologie::TBC::{sub}",
                "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Infektiologie::TBC",
                "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::(fächerübergreifend)_Behandlungsanlässe::Husten::TBC",
                "#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::M2-100-Tage-Lernplan::M2_Lerntag_010_Infektiologie::TBC",
                "#Ankizin_vAnkiCollab::#UNIVERSITÄTEN::Uni_Berlin::Block_TBC::TBC",
            ],
            suspended=True,
        )
        shared_cids.extend(cids)

    # Radiologie::TBC has 3 distinct notes (more than Innere::Pneumologie::TBC's 2) -> must NOT converge away,
    # and loses #1 spot ONLY when Innere::Pneumologie::TBC has greater convergence
    _, rad_extra = add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Radiologie::TBC"],
        suspended=True,
    )
    for _ in range(2):
        add_ankizin_note(
            tmp_col,
            did,
            ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Radiologie::TBC"],
            suspended=True,
        )

    # Non-overlapping pair ("KardioTest") to verify biggest card count wins #1 when convergence == 0
    add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Chirurgie::KardioTest_Klein"],
        suspended=True,
    )
    for _ in range(3):
        add_ankizin_note(
            tmp_col,
            did,
            ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Innere::KardioTest_Gross"],
            suspended=True,
        )

    # Distinct topic with 19 active + 1 suspended new card + 1 paused child card -> 19/21 = 90.5% active (>=90%)
    for _ in range(19):
        add_ankizin_note(
            tmp_col,
            did,
            ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Kardiologie::Hypertonie"],
            suspended=False,
        )
    _, straggler_cids = add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Kardiologie::Hypertonie"],
        suspended=True,
    )
    add_ankizin_note(
        tmp_col,
        did,
        ["#Ankizin_vAnkiCollab::#M2_M3_Klinik::#AMBOSS::#Bibliothek-Klinik::Kardiologie::Hypertonie::Sekundärformen"],
        suspended=True,
    )

    idx = build_tag_index(tmp_col)

    # 1. Nested search preserves hierarchy & collapses 100%-identical TBC sets to 1 canonical AMBOSS hit
    ns = idx.filter_tree_nested("TBC", category_key="amboss", yield_preset="all")
    innere_tbc_key = "amboss::innere::pneumologie::tbc"
    infek_tbc_key = "amboss::infektiologie::tbc"
    radio_tbc_key = "amboss::radiologie::tbc"
    assert innere_tbc_key in ns.hit_keys
    assert radio_tbc_key in ns.hit_keys
    assert infek_tbc_key not in ns.hit_keys
    assert innere_tbc_key in ns.aliases and any("Infektiologie" in a for a in ns.aliases[innere_tbc_key])
    assert "amboss::innere" in ns.expand_keys
    assert "amboss::innere::pneumologie" in ns.expand_keys
    assert innere_tbc_key not in ns.expand_keys  # matched parent stays collapsed with subtopics underneath

    # 2. Cross-category search also converges cross-cutting Husten, Lernplan & Uni paths under AMBOSS canonical hit
    cross_hits, cross_aliases = idx.search_tree_converged("TBC", category_key=None, yield_preset="all")
    assert {n.key for n in cross_hits} == {innere_tbc_key, radio_tbc_key}
    assert cross_hits[0].key == innere_tbc_key  # highest convergence beats larger 3-card non-converged Radiologie::TBC
    assert len(cross_aliases[innere_tbc_key]) == 4  # Infektiologie + Behandlungsanlässe/Husten + 100-Tage-Plan + Uni Berlin
    assert not any("Husten" in n.breadcrumb for n in cross_hits)

    # 2b. With zero convergence/overlap, the topic with the most notes/cards ranks #1
    non_ov_hits, non_ov_aliases = idx.search_tree_converged("KardioTest", category_key="amboss", yield_preset="all")
    assert non_ov_aliases == {}
    assert [n.display_name for n in non_ov_hits] == ["KardioTest Gross", "KardioTest Klein"]

    # 3. Direct RAM filtered_card_ids & fast refresh_card_states without re-parsing note tags
    tbc_node = idx.by_key[innere_tbc_key]
    assert idx.filtered_card_ids([tbc_node], yield_preset="all", only_suspended=True) == sorted(shared_cids)

    tmp_col.sched.unsuspend_cards(shared_cids[:1])
    c1 = tmp_col.get_card(shared_cids[0])
    c1.type = 2
    c1.queue = 2
    c1.ivl = 30
    tmp_col.update_card(c1)

    idx2 = refresh_card_states(tmp_col, idx)
    st_after = idx2.by_key[innere_tbc_key].stats(yield_preset="all", exclude_zahni=False)
    assert st_after.active == 1
    assert st_after.suspended == 1
    assert st_after.mature_count == 1
    assert st_after.new_count == 1

    # 4. Nachzügler picks ONLY the 1 suspended new card on Hypertonie (ignoring paused child Sekundärformen)
    topics, found_stragglers = find_stragglers(idx2, category_key="amboss", yield_preset="all")
    assert topics == 1
    assert found_stragglers == straggler_cids
    assert rad_extra[0] not in found_stragglers
