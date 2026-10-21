import webbrowser
import aqt
import anki
import re

from aqt import mw
from aqt.qt import *
from aqt.operations import QueryOp, CollectionOp
from anki.collection import EmptyCardsReport, OpChanges
from aqt.emptycards import EmptyCardsDialog
from aqt.utils import showInfo, askUser, showWarning, tooltip
from .lernplan_decks import DeckResult


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
    pattern = re.compile(r"#(Ankizin_v(\d+|Ankihub|AnkiCollab)|Zankiphil)::")
    versions = []
    for tag in col.tags.all():
        match = pattern.match(tag)
        if match:
            if match.group(2):  # Ankizin_v case
                version = "v" + match.group(2)
            else:  # Zankiphil case
                version = "Zankiphil"
            
            if version not in versions:
                versions.append(version)

    # sorting: AnkiCollab first, then Ankihub, then numbers in decreasing order, then Zankiphil
    def sort_key(version):
        if version == "vAnkiCollab":
            return (0, 0)  # highest priority
        elif version == "vAnkihub":
            return (1, 0)
        elif version == "Zankiphil":
            return (3, 0)
        elif version.startswith("v") and version[1:].isdigit():
            return (1, -int(version[1:]))  # negative for decreasing order
        else:
            return (4, version)
    
    versions.sort(key=sort_key)
    return versions


def report_result(result: DeckResult, silent: bool = False) -> None:
    """Show failures (always) and decks without cards (unless silent). Main thread only."""
    if result.failed:
        showWarning("<br><br>".join(f"<b>{name}</b>: {msg}" for name, msg in result.failed))
    elif result.skipped and not silent:
        tooltip(f"{len(result.skipped)} Stapel ohne Karten wurden nicht erstellt (z.B. keine TOP-100/High-Yield Karten an diesem Tag).", period=5000)
