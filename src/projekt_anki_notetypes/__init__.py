from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Sequence

if TYPE_CHECKING:
    from anki.notes import Note, NoteId

from anki.utils import ids2str
import aqt.editor
from aqt import mw
from aqt.qt import QUrl, QPixmap
from aqt.browser import Browser
from aqt.editor import EditorWebView
from aqt.operations.note import update_note
from aqt.gui_hooks import (
    browser_will_show_context_menu,
    card_layout_will_show,
    profile_did_open,
    editor_will_show_context_menu,
    webview_will_show_context_menu,
)
from aqt.qt import QMenu, QPushButton, qtmajor
from aqt.utils import askUserDialog, tooltip

from bs4 import BeautifulSoup

from .butler.init import init_butler
from .compat import add_compat_aliases
from .constants import ADDON_DIR_NAME, ADDON_VERSION
from .gui.config_window import (
    NotetypesConfigWindow,
    models_with_available_updates,
    note_type_version,
)
from .gui.menu import setup_menu
from .gui.utils import choose_subset
from .notetype_setting_definitions import (
    HINT_BUTTONS,
    projekt_anki_notetype_models,
)

RESOURCES_PATH = Path(__file__).parent / "resources"


# init Butler sub-component
def setup_butler():
    init_butler()


def setup():
    add_compat_aliases()
    setup_menu(open_window)
    card_layout_will_show.append(add_button_to_clayout)
    replace_default_addon_config_action()
    profile_did_open.append(on_profile_did_open)
    browser_will_show_context_menu.append(on_browser_will_show_context_menu)
    editor_will_show_context_menu.append(on_editor_will_show_context_menu)
    webview_will_show_context_menu.append(on_webview_will_show_context_menu)


def on_profile_did_open():
    copy_resources_into_media_folder()
    from .onboarding.engine import detect_setup_state, get_setup_state

    if get_setup_state().get("resume") or detect_setup_state()["scenario"] != "ready":
        return
    maybe_show_notetypes_update_notice()
    maybe_show_deck_update_notice()


def open_window():
    window = NotetypesConfigWindow()
    window.open()


def add_button_to_clayout(clayout):
    button = QPushButton()
    button.setAutoDefault(False)
    button.setText("Ankizin Notiztypen konfigurieren")

    def open_window_with_clayout():
        window = NotetypesConfigWindow(clayout)
        window.open()

    button.clicked.connect(open_window_with_clayout)
    clayout.buttons.insertWidget(1, button)


def maybe_show_notetypes_update_notice():
    # can happen when restoring data from backup
    if not mw.col:
        return

    models_with_updates = models_with_available_updates()
    if not models_with_updates:
        return

    # Return early if user was already notified about this version (and didn't choose "Remind me later")
    latest_version = note_type_version(projekt_anki_notetype_models()[0])

    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if latest_version == conf.get("latest_notified_note_type_version"):
        return

    answer = askUserDialog(
        title="Ankizin Notiztypen-Update",
        text="Es ist eine neue Version der Ankizin Notiztypen verfügbar!<br>"
        "Du kannst dich im neuen Fenster gleich entscheiden, ob du sie herunterladen willst.<br>"
        "(Button '<code>Aktualisiere Notiztypen</code>')<br><br>"
        "Kann ich das Add-On-Fenster öffnen?",
        buttons=reversed(["Ja", "Nein", "Erinnere mich später!"]),
    ).run()
    if answer == "Ja":
        conf["latest_notified_note_type_version"] = latest_version
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
        open_window()
    elif answer == "Nein":
        conf["latest_notified_note_type_version"] = latest_version
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
    elif answer == "Erinnere mich später!":
        # Don't update the config, so the user will be asked again next time
        pass


def _major_minor(version: Optional[str]) -> Optional[str]:
    """'6.3.2' -> '6.3', so that fix releases (6.3.1, 6.3.2, ...) don't count as a new version."""
    return ".".join(version.split(".")[:2]) if version else None


# NOTE: the text has to be updated manually each time ADDON_VERSION gets a new major/minor version (v6.4, v7, ...);
# fix releases (v6.3.2) don't show the notice again
def maybe_show_deck_update_notice():
    # can happen when restoring data from backup
    if not mw.col:
        return

    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if _major_minor(ADDON_VERSION) == _major_minor(conf.get("latest_notified_deck_version")):
        return

    update_dialog = askUserDialog(
        title="Ankizin Notiztypen-Update",
        text="<h1>NOVEMBER-UPDATE: Neues im Lernplan-Manager</h1>"
        "<ul>"
        "<li><b>Eigene Reihenfolge:</b> Lerntage per Drag &amp; Drop umsortieren und als gelernt abhaken</li>"
        "<li><b>Fortschritt &amp; Prognose:</b> alle Lerntage als farbige Kacheln, voraussichtliches Plan-Ende und Puffer bis zum M2-Termin (M2 F27 oder M2 H27)</li>"
        "<li><b>Zusatz- und Pausentage</b> per Kalender; der Lernplan lässt sich als Kalender-Datei (.ics) exportieren</li>"
        "</ul>"
        "<b>Außerdem:</b> Performance-Verbesserungen und stabilere Karten (Button <i>Aktualisiere Notiztypen</i>).<br><br>"
        "Fortschritt, Prognose, Kalender und .ics stammen aus <i>Ankizin-Lernplan Plus</i> von Lukas Schaffner.<br><br>"
        "Zur Erinnerung: Ankizin ist <a href='https://www.ankizin.de/wiki/umzug-ankihub-auf-ankicollab/'>zu AnkiCollab umgezogen</a>.<br><br>"
        "<small><i>Dieses Pop-Up kommt einmal pro Version, bis du auf 'Verstanden' klickst.</i></small>",
        buttons=reversed(
            [
                "Verstanden",
                "Erinnere mich später!",
            ]
        ),
    )
    update_dialog.setIconPixmap(QPixmap("icons:ankizin.png"))
    update_dialog.setMaximumHeight(500)

    answer = update_dialog.run()
    if answer == "Verstanden":
        conf["latest_notified_deck_version"] = ADDON_VERSION
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
    else:
        # Don't update the config, so the user will be asked again next time
        pass


def copy_resources_into_media_folder():
    # add resources of all notetypes to collection media folder
    media = mw.col.media
    for file in RESOURCES_PATH.iterdir():
        # add_file would store a changed file as "name-<hash>.ext", so the templates would keep
        # using the old one: trash the outdated copy first (identical files are left untouched)
        target = Path(media.dir()) / file.name
        if target.exists() and target.read_bytes() != file.read_bytes():
            media.trash_files([file.name])
        media.add_file(str(file))


def replace_default_addon_config_action():
    mw.addonManager.setConfigAction(ADDON_DIR_NAME, open_window)


def hint_fields_for_nids(nids: Sequence["NoteId"]) -> List[str]:
    all_fields = mw.col.db.list(
        "select distinct name from fields where ntid in (select distinct mid from notes where id in %s)"
        % ids2str(nids)
    )
    hint_fields = []
    for field in all_fields:
        if field in HINT_BUTTONS.values():
            hint_fields.append(field)
    return hint_fields


def note_autoopen_fields(note: "Note") -> List[str]:
    tags = []
    prefix = "autoopen::"
    for tag in note.tags:
        if tag.startswith(prefix):
            tags.append(tag[len(prefix) :].replace("_", " "))
    return tags


def on_auto_reveal_fields_action(
    browser: Browser, selected_nids: Sequence["NoteId"]
) -> None:
    fields = hint_fields_for_nids(selected_nids)
    if not fields:
        tooltip(
            "Kein Hinweisfeld in den ausgewählten Karten gefunden.",
            parent=browser,
        )
        return
    current = (
        note_autoopen_fields(mw.col.get_note(selected_nids[0]))
        if len(selected_nids) == 1
        else []
    )
    chosen = choose_subset(
        "Entscheide welche Felder der ausgewählten Karten automatisch aufgedeckt werden sollen<br>",
        choices=fields,
        current=current,
        description_html="Das wird die autoopen::field_name tags der Karten editieren.",
        parent=browser,
    )
    if chosen is None:
        return
    autoopen_tags = []
    for field in chosen:
        autoopen_tags.append(f"autoopen::{field.lower().replace(' ', '_')}")

    def task() -> None:
        notes = [mw.col.get_note(nid) for nid in selected_nids]
        for note in notes:
            note.tags = [
                tag for tag in note.tags if not tag.startswith("autoopen::")
            ] + autoopen_tags
        mw.col.update_notes(notes)  # one undo step; Note.flush() is deprecated

    def on_done(fut: Future) -> None:
        mw.progress.finish()
        browser.onReset()
        fut.result()

    mw.progress.start(label="Karten werden aktualisiert...", immediate=True)
    mw.taskman.run_in_background(task, on_done)


def on_browser_will_show_context_menu(
    browser: Browser, context_menu: QMenu
) -> None:
    selected_nids = browser.selectedNotes()
    action = context_menu.addAction(
        "Ankizin: Felder automatisch aufdecken",
        lambda: on_auto_reveal_fields_action(browser, selected_nids),
    )
    if not selected_nids:
        action.setDisabled(True)


def toggle_image_class(html: str, src: str, name: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for img in soup("img"):
        if img.get("src", "").strip("/") != src:
            continue
        classes = img.get("class", [])
        if name in classes:
            classes.remove(name)
        else:
            classes.append(name)
        if classes:
            img["class"] = classes
        else:
            img.attrs.pop("class", None)
    return soup.decode_contents()


def image_has_class(html: str, src: str, name: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return any(
        name in img.get("class", [])
        for img in soup("img")
        if img.get("src", "").strip("/") == src
    )


def on_editor_will_show_context_menu(
    webview: EditorWebView, menu: QMenu
) -> None:
    if qtmajor >= 6:
        data = webview.lastContextMenuRequest()  # type: ignore
    else:
        data = webview.page().contextMenuData()
    url = data.mediaUrl()
    editor = webview.editor
    idx = editor.currentField
    if not url.isValid() or idx is None:
        return

    # The legacy editor holds the note itself. The new one (experimental) keeps it in the
    # web view, so we edit the saved note instead and let the editor reload it.
    legacy = hasattr(editor, "note")
    if legacy:
        note = editor.note
    elif editor.nid:
        note = mw.col.get_note(editor.nid)
    else:
        return  # new editor in add mode: nothing is saved yet

    if url.matches(QUrl(mw.serverURL()), QUrl.UrlFormattingOption.RemovePath):
        src = url.path().strip("/")
    else:
        src = url.toString()

    def toggle(name: str) -> None:
        if legacy:
            editor.note.fields[idx] = toggle_image_class(editor.note.fields[idx], src, name)
            editor.loadNoteKeepingFocus()
            return

        def save_and_reload() -> None:  # runs once unsaved edits are saved
            fresh = mw.col.get_note(editor.nid)
            fresh.fields[idx] = toggle_image_class(fresh.fields[idx], src, name)
            update_note(parent=webview, note=fresh).success(
                lambda _: editor.reload_note()
            ).run_in_background()

        editor.call_after_note_saved(save_and_reload)

    def add(name: str, text_on: str, text_off: str) -> None:
        active = image_has_class(note.fields[idx], src, name)
        menu.addAction(text_off if active else text_on, lambda: toggle(name))

    menu.addSeparator()
    add("blur", "Ankizin: Bild weichzeichnen", "Ankizin: Bild nicht mehr weichzeichnen")
    add("invert", "Ankizin: Bild invertieren", "Ankizin: Bild nicht mehr invertieren")
    menu.addSeparator()


# NewEditorWebView only exists in newer Anki, and it fires no editor-specific menu hook
NEW_EDITOR_WEBVIEW = getattr(aqt.editor, "NewEditorWebView", ())


def on_webview_will_show_context_menu(webview, menu: QMenu) -> None:
    if isinstance(webview, NEW_EDITOR_WEBVIEW):
        on_editor_will_show_context_menu(webview, menu)


if mw is not None:
    setup()
    setup_butler()
