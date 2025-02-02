import webbrowser
import aqt
import anki
import re

from aqt import mw
from aqt.qt import *
from aqt.operations import QueryOp, CollectionOp
from anki.collection import EmptyCardsReport, OpChanges
from aqt.emptycards import EmptyCardsDialog
from aqt.utils import showInfo, askUser, showWarning
from anki.decks import FilteredDeckConfig
from anki.scheduler import FilteredDeckForUpdate
from anki.errors import FilteredDeckError


def on_success(out: OpChanges) -> None:
    showInfo("Fertig! Viel Spaß mit Ankizin!")
    aqt.mw.reset()


def fix_integrity_inner() -> OpChanges:
    aqt.mw.col.fix_integrity()
    return OpChanges()


def fix_integrity() -> None:
    CollectionOp(parent=aqt.mw, op=lambda _: fix_integrity_inner()).success(
        on_success
    ).run_in_background()


def async_general_housekeeping() -> None:
    def on_success(report: EmptyCardsReport) -> None:
        if report.notes:
            print(f"Deleting {report.notes} notes")
            dialog = EmptyCardsDialog(aqt.mw, report)
            dialog._delete_cards(keep_notes=True)

        # Cheesy af, ich will das async machen aber erst nachdem sicher alle Karten gelöscht wurden. Also spawn ich hier noch ne op
        print("Fixing collection integrity")
        aqt.mw.progress.finish()  # finish bc collectionOp will spawn a new one
        fix_integrity()

    def op(col) -> EmptyCardsReport:
        empty_cards_report = col.get_empty_cards()
        print("Clearing unused tags")
        col.tags.clear_unused_tags()
        return empty_cards_report

    QueryOp(parent=aqt.mw, op=op, success=on_success).with_progress(
        f"Finale Änderungen werden durchgeführt..."
    ).run_in_background()


def has_ankizin_installed():
    # Check for Ankizin deck or tags
    collection = aqt.mw.col
    has_ankizin = False

    # Check deck names
    for deck in collection.decks.all():
        if "ankizin" in deck["name"].lower():
            has_ankizin = True
            break

    # Check tags
    if not has_ankizin:
        for tag in collection.tags.all():
            if "#Ankizin_v" in tag.lower():
                has_ankizin = True
                break

    return has_ankizin


def check_ankizin_installation():
    has_ankizin = has_ankizin_installed()
    if not has_ankizin:
        if askUser(
            "Ankizin Deck nicht gefunden. Möchtest du die Download-Seite öffnen?"
        ):
            webbrowser.open("https://rebrand.ly/ankizin")
    return has_ankizin


# NOTE: This function is not used in the current codebase due to missing anyward compatibility
# other than to display the version in the settings dialog
def get_ankizin_versions() -> list:
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    # Determine the latest Ankizin_v version dynamically
    pattern = re.compile(r"#Ankizin_v(\d+|Ankihub)::")
    versions = []
    for tag in col.tags.all():
        match = pattern.match(tag)
        if match:
            versions.append("v" + match.group(1))

    return versions


def create_filtered_deck(deck_name, search, unsuspend=True, silent=False):
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    deck_id = col.decks.id_for_name(deck_name)
    if deck_id != None:
        col.sched.rebuild_filtered_deck(deck_id)
        return

    if unsuspend:
        # Unsuspend all cards that are not yet unsuspended, sonst nicht im dynamic deck
        cidsToUnsuspend = col.find_cards(search)
        col.sched.unsuspend_cards(cidsToUnsuspend)

    if not silent:
        mw.progress.start()
    # deck_id = 0
    deck: FilteredDeckForUpdate = col.sched.get_or_create_filtered_deck(0)

    deck.name = deck_name
    config = deck.config
    config.reschedule = 1
    terms = [
        FilteredDeckConfig.SearchTerm(
            search=search,
            limit=999,
            order=5,  # order by added date, so its chronological (usually)
        )
    ]

    del config.delays[:]  # v1 scheduler relict
    del config.search_terms[:]
    config.search_terms.extend(terms)

    if not silent:
        mw.progress.finish()
    try:
        col.sched.add_or_update_filtered_deck(deck)
    except FilteredDeckError as e:
        print(f"Error: {e}")
        if not silent:
            showWarning(f"Error: {e}")


def remove_filtered_deck(deck_id):
    col = mw.col
    if col is None:
        raise Exception("collection not available")

    mw.progress.start()

    col.sched.empty_filtered_deck(deck_id)
    col.decks.remove([deck_id])

    mw.progress.finish()
    mw.reset()
