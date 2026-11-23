"""Unit tests for ankizin.study_hub.tag_index."""
from __future__ import annotations

from ankizin.study_hub.tag_index import (
    build_tag_index,
    build_topic_search,
    fetch_topic_preview,
    format_topic_label,
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
