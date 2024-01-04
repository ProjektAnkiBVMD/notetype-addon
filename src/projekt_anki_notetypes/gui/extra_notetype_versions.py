import re
from concurrent.futures import Future
from copy import deepcopy
from typing import Dict, List

from aqt import mw
from aqt.utils import askUser, tooltip

from ..constants import NOTETYPE_COPY_RE
from ..notetype_setting_definitions import projekt_anki_notetype_names
from ..utils import adjust_field_ords, create_backup


def handle_extra_notetype_versions() -> None:
    # mids of copies of the AnKing notetype identified by its name
    copy_mids_by_notetype_base_name: Dict[str, List[int]] = dict()
    for notetype_base_name in projekt_anki_notetype_names():
        if mw.col.models.by_name(notetype_base_name) is None:
            continue

        model_copy_mids = [
            x.id
            for x in mw.col.models.all_names_and_ids()
            if re.match(
                NOTETYPE_COPY_RE.format(notetype_base_name=notetype_base_name), x.name
            )
        ]
        if model_copy_mids:
            copy_mids_by_notetype_base_name[notetype_base_name] = model_copy_mids

    if not copy_mids_by_notetype_base_name:
        return

    if not askUser(
        "Es gibt ein paar Duplikate der Projekt Anki Notiztypen. Willst du alle Notiztypen mit Namen wie "
        '"ProjektAnkiCloze-1dgs0" zu "ProjektAnkiCloze" konvertieren?\n\n'
        "Das wird alle Notizen mit dem Notiztyp ändern und die Duplikate löschen. Die Änderungen benötigen eine Vollsynchronisation mit AnkiWeb. "
        "Ein Backup wird automatisch erstellt bevor die Änderungen angewendet werden.\n\n"
        "Egal wie du dich entscheidest wird sich das Notiztyp Fenster öffnen.",
        title="Duplikate der Projekt Anki Notiztypen",
    ):
        return

    mw.taskman.with_progress(
        create_backup,
        on_done=lambda future: convert_extra_notetypes(
            future, copy_mids_by_notetype_base_name
        ),
        label="Erstelle Backup...",
        immediate=True,
    )


def convert_extra_notetypes(
    future: Future, copy_mids_by_notetype_base_name: Dict[str, List[int]]
) -> None:
    """
    Change note type of notes that have copies of an AnKing note type as a type to the original note type.
    Remove the extra note type copies.
    """

    future.result()  # throws an exception if there was an exception in the background task

    for notetype_base_name, copy_mids in copy_mids_by_notetype_base_name.items():
        model = mw.col.models.by_name(notetype_base_name)
        for copy_mid in copy_mids:
            model_copy = mw.col.models.get(copy_mid)  # type: ignore

            # First change the <model_copy> to be exactly like <notetype> to then be able to
            # change the note type of notes of type <model_copy> without problems
            new_model = deepcopy(model)
            new_model["id"] = model_copy["id"]
            new_model["name"] = model_copy["name"]  # to prevent duplicates
            new_model["usn"] = -1  # triggers full sync
            new_model = adjust_field_ords(model_copy, new_model)
            mw.col.models.update_dict(new_model)

            # change the notes of type <model_copy> to type <notetype>
            nids_with_model_copy_type = mw.col.find_notes(
                f'"note:{model_copy["name"]}"'
            )
            mw.col.models.change(
                model_copy,
                nids_with_model_copy_type,  # type: ignore
                model,
                {i: i for i in range(len(model["flds"]))},
                None,
            )

            # remove the notetype copy
            mw.col.models.remove(copy_mid)  # type: ignore

    mw.reset()
    tooltip("Notiztypen wurden erfolgreich konvertiert.")
