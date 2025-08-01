from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, List, Sequence

if TYPE_CHECKING:
    from anki.notes import Note, NoteId

from anki.utils import ids2str
from aqt import mw
from aqt.qt import QUrl, QAction, QMessageBox, QSize, QIcon, QPixmap
from aqt.browser import Browser
from aqt.editor import EditorWebView
from aqt.gui_hooks import (
    browser_will_show_context_menu,
    card_layout_will_show,
    profile_did_open,
    editor_will_show_context_menu,
)
from aqt.qt import QMenu, QPushButton, qtmajor, QAction, qconnect
from aqt.utils import askUserDialog, tooltip, openLink

from bs4 import BeautifulSoup

from .compat import add_compat_aliases
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

ADDON_DIR_NAME = str(Path(__file__).parent.name)
ADDON_VERSION = "5.4"
RESOURCES_PATH = Path(__file__).parent / "resources"

from .butler.init import init_butler


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


def on_profile_did_open():
    copy_resources_into_media_folder()
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


# NOTE: has to be updated manually each time there is a new major version
def maybe_show_deck_update_notice():
    # can happen when restoring data from backup
    if not mw.col:
        return

    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if ADDON_VERSION == conf.get("latest_notified_deck_version"):
        return

    update_dialog = askUserDialog(
        title="Ankizin Deck-Update",
        text="<h1>Ankizin V5 IST DA! (endlich)</h1>"
        "<h2>Neue Karten und verbesserte Tags für eine noch bessere StEx-Vorbereitung!</h2>"
        "<h2>Was ist neu?</h2>"
        "<ul>"
        "<li>Neue und mehr Lernplan-Manager-Optionen</li>"
        "<li>5441 neue Klinik- / M2-Karten</li>"
        "<li>1055 neue Vorklinik- / M1-Karten</li>"
        "<li>Neue Struktur für IMPP-Fokus / Yield-Tags</li>"
        "<li>Etliche neue Uni-Tags</li>"
        "<li>Verbesserte Karten- und Notiztypen</li>"
        "</ul>"
        "<h2>Was sollst du nun tun?</h2>"
        "Die neue Ankizin-Version herunterladen!<br>"
        "<h2>Ich nutze aber AnkiHub, was gilt für mich?</h2>"
        "Du musst nix machen, Updates kommen automatisch.<br>",
        buttons=reversed(
            [
                "Ich bin schon up-to-date",
                "Erinnere mich später!",
            ]
        ),
    )
    update_dialog.setIconPixmap(QPixmap("icons:ankizin.png"))
    update_dialog.setMaximumHeight(500)
    # update_dialog.setIconSize(QSize(62, 62))
    link_button = update_dialog.addButton(
        "ZUM DOWNLOAD!", QMessageBox.ButtonRole.RejectRole
    )
    link_button_url = "https://www.ankizin.de/wiki/ankizin-deck-installieren/"
    # link_button_url = "https://www.youtube.com/watch?v=3CKUXRVaiLs"
    link_button.clicked.connect(lambda _, url=link_button_url: openLink(url))

    answer = update_dialog.run()
    if (
        # answer == "Erklärvideo öffnen!"
        # answer == "Das ist ja super!"
        answer == "Ich bin schon up-to-date"
    ):
        conf["latest_notified_deck_version"] = ADDON_VERSION
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
    elif answer == "Erinnere mich später!":
        # Don't update the config, so the user will be asked again next time
        pass


def copy_resources_into_media_folder():
    # add resources of all notetypes to collection media folder
    for file in Path(RESOURCES_PATH).iterdir():
        # if not mw.col.media.have(file.name):
        #     mw.col.media.add_file(str(file.absolute()))
        mw.col.media.add_file(str(file.absolute()))


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
            tags.append(
                tag[tag.index(prefix) + len(prefix) :].replace("_", " ")
            )
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
        notes = []
        for nid in selected_nids:
            note = mw.col.get_note(nid)
            notes.append(note)
            new_tags = []
            for tag in note.tags:
                if not tag.startswith("autoopen::"):
                    new_tags.append(tag)
            new_tags.extend(autoopen_tags)
            note.tags = new_tags
            note.flush()

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
    context_menu.addAction(action)
    if not selected_nids:
        action.setDisabled(True)


def on_editor_will_show_context_menu(
    webview: EditorWebView, menu: QMenu
) -> None:
    def helper() -> None:
        editor = webview.editor
        url = data.mediaUrl()
        if url.matches(
            QUrl(mw.serverURL()), QUrl.UrlFormattingOption.RemovePath
        ):
            src = url.path().strip("/")
        else:
            src = url.toString()
        field = editor.note.fields[editor.currentField]
        soup = BeautifulSoup(field, "html.parser")
        return editor, src, soup

    def is_blur_image() -> bool:
        _, src, soup = helper()
        for img in soup("img"):
            if img.get("src", "").strip("/") != src:
                continue
            classes = img.get("class", [])
            if "blur" in classes:
                return True
        return False

    def on_blur_image() -> None:
        editor, src, soup = helper()
        for img in soup("img"):
            if img.get("src", "").strip("/") != src:
                continue
            classes = img.get("class", [])
            if "blur" in classes:
                classes.remove("blur")
            else:
                classes.append("blur")
            if classes:
                img["class"] = classes
            elif "class" in img.attrs:
                del img["class"]
        editor.note.fields[editor.currentField] = soup.decode_contents()
        editor.loadNoteKeepingFocus()

    def is_invert_image() -> bool:
        _, src, soup = helper()
        for img in soup("img"):
            if img.get("src", "").strip("/") != src:
                continue
            classes = img.get("class", [])
            if "invert" in classes:
                return True
        return False

    def on_invert_image() -> None:
        editor, src, soup = helper()
        for img in soup("img"):
            if img.get("src", "").strip("/") != src:
                continue
            classes = img.get("class", [])
            if "invert" in classes:
                classes.remove("invert")
            else:
                classes.append("invert")
            if classes:
                img["class"] = classes
            elif "class" in img.attrs:
                del img["class"]
        editor.note.fields[editor.currentField] = soup.decode_contents()
        editor.loadNoteKeepingFocus()

    if qtmajor >= 6:
        data = webview.lastContextMenuRequest()  # type: ignore
    else:
        data = webview.page().contextMenuData()
    if data.mediaUrl().isValid():
        menu.addSeparator()
        blur_image_action = (
            QAction(
                "Ankizin: Bild nicht mehr weichzeichnen",
                menu,
            )
            if is_blur_image()
            else QAction(
                "Ankizin: Bild weichzeichnen",
                menu,
            )
        )
        qconnect(blur_image_action.triggered, on_blur_image)
        menu.addAction(blur_image_action)

        invert_image_action = (
            QAction(
                "Ankizin: Bild nicht mehr invertieren",
                menu,
            )
            if is_invert_image()
            else QAction(
                "Ankizin: Bild invertieren",
                menu,
            )
        )
        qconnect(invert_image_action.triggered, on_invert_image)
        menu.addAction(invert_image_action)
        menu.addSeparator()


if mw is not None:
    setup()
    setup_butler()
