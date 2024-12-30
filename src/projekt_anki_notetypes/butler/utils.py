from aqt.qt import *
from aqt.operations import QueryOp, CollectionOp
from anki.collection import EmptyCardsReport, OpChanges
from aqt.emptycards import EmptyCardsDialog
from aqt.utils import showInfo, askUser

import webbrowser
import aqt

def on_success(out: OpChanges) -> None:
    showInfo("Fertig! Viel Spaß mit Ankizin!")
    aqt.mw.reset()
    
def fix_integrity_inner() -> OpChanges:
    aqt.mw.col.fix_integrity()
    return OpChanges()

def fix_integrity() -> None:
    CollectionOp(
        parent=aqt.mw,
        op=lambda _: fix_integrity_inner() 
    ).success(on_success).run_in_background()
    
def async_general_housekeeping() -> None:
    def on_success(report: EmptyCardsReport) -> None:
        if report.notes:
            print(f"Deleting {report.notes} notes")
            dialog = EmptyCardsDialog(aqt.mw, report)
            dialog._delete_cards(keep_notes=True)
        
        # Cheesy af, ich will das async machen aber erst nachdem sicher alle Karten gelöscht wurden. Also spawn ich hier noch ne op
        print("Fixing collection integrity")
        aqt.mw.progress.finish() # finish bc collectionOp will spawn a new one
        fix_integrity()

    def op(col) -> EmptyCardsReport:
        empty_cards_report = col.get_empty_cards()
        print("Clearing unused tags")
        col.tags.clear_unused_tags()
        return empty_cards_report

    QueryOp(
        parent=aqt.mw,
        op=op,
        success=on_success
    ).with_progress(f"Paar finale Änderungen noch...").run_in_background()

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
        if askUser("Ankizin Deck nicht gefunden. Möchtest du die Download-Seite öffnen?"):
            webbrowser.open("https://rebrand.ly/ankizin")
    return has_ankizin