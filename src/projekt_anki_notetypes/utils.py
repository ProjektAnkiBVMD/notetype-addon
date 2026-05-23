import time
from copy import deepcopy
from typing import Dict, List

from aqt import mw

from .notetype_setting_definitions import projekt_anki_notetype_model

try:
    from anki.models import NotetypeDict  # type: ignore # pylint: disable=unused-import
except:
    pass


def update_notetype_to_newest_version(
    model: "NotetypeDict", notetype_base_name: str
) -> None:
    new_model = projekt_anki_notetype_model(notetype_base_name)
    new_model["id"] = model["id"]
    new_model["name"] = model["name"]  # keep the name
    new_model["mod"] = int(time.time())  # not sure if this is needed
    new_model["usn"] = -1  # triggers full sync

    new_model["flds"] = adjust_fields(model["flds"], new_model["flds"])

    model.update(new_model)


def adjust_fields(
    cur_model_fields: List[Dict], new_model_fields: List[Dict]
) -> List[Dict]:
    """
    Prepares note type fields for updates by merging fields from the current and new models.

    This function handles several operations when updating note types:
    1. Maintains field content mapping by assigning appropriate 'ord' values to matching fields
    2. Assigns high 'ord' values to new fields so they start empty
    3. Appends fields that only exist locally to the new model

    Returns:
        Updated note type fields
    """
    new_model_fields = deepcopy(new_model_fields)

    cur_model_field_map = {
        field["name"].lower(): field["ord"] for field in cur_model_fields
    }

    # Set appropriate ord values for each new field
    for new_model_field in new_model_fields:
        field_name_lower = new_model_field["name"].lower()
        if field_name_lower in cur_model_field_map:
            # If field exists in current model, preserve its ord value
            new_model_field["ord"] = cur_model_field_map[field_name_lower]
        else:
            # For new fields, set ord to a value outside the range of current fields
            new_model_field["ord"] = len(cur_model_fields) + 1

    # Append fields that only exist locally to the new model
    new_model_field_names = {field["name"].lower() for field in new_model_fields}
    only_local_fields = [
        field
        for field in cur_model_fields
        if field["name"].lower() not in new_model_field_names
    ]

    final_fields = new_model_fields + only_local_fields

    return final_fields


def create_backup() -> None:
    try:
        mw.col.create_backup(
            backup_folder=mw.pm.backupFolder(),
            force=True,
            wait_for_completion=True,
        )
    except AttributeError:  # < 2.1.50
        mw.col.close(downgrade=False)
        mw.backup()  # type: ignore
        mw.col.reopen(after_full_sync=False)
