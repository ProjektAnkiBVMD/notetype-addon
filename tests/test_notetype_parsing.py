import json
import unittest
from collections import defaultdict

from src.projekt_anki_notetypes.gui.config_window import ntss_for_model
from src.projekt_anki_notetypes.notetype_setting_definitions import (
    projekt_anki_notetype_model,
    projekt_anki_notetype_names,
)


class TestNotetypeSettingParsing(unittest.TestCase):
    def test_nts_parsing(self):
        current = defaultdict(dict)
        for notetype_name, model in (
            (name, projekt_anki_notetype_model(name))
            for name in projekt_anki_notetype_names()
        ):
            ntss = ntss_for_model(model)
            for nts in ntss:
                setting_name = nts.config["name"]
                setting_value = nts.setting_value(model)
                current[notetype_name][setting_name] = setting_value

        with open("tests/expected.json", "r") as f:
            expected = json.load(f)

        with open("tests/current.json", "w") as f:
            json.dump(current, f, sort_keys=True)

        self.assertDictEqual(dict(current), dict(expected))
