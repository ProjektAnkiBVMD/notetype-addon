# doesn't work standalone, it can be put into the add-on to work

import json
from pathlib import Path

from aqt import mw
from src.projekt_anki_notetypes.notetype_setting_definitions import (
    projekt_anki_notetype_templates,
)

output_path = Path(__file__).parent / "models"
for notetype_name in projekt_anki_notetype_templates().keys():
    with open(output_path / f"{notetype_name}.json", "w") as f:
        model = mw.col.models.by_name(notetype_name)
        model["css"] = ""
        model["tmpls"][0]["qfmt"] = ""
        model["tmpls"][0]["afmt"] = ""
        model["id"] = 0
        f.write(json.dumps(model))
