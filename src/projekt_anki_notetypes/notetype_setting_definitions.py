import json
import re
from pathlib import Path
from typing import Any, Dict, List, OrderedDict, Tuple, Union

try:
    from anki.models import NotetypeDict  # pylint: disable=unused-import
except:
    pass

PROJEKT_ANKI_NOTETYPES_PATH = Path(__file__).parent / "note_types"

# Regular expression for fields for which the add-on offers settings aka configurable fields.
# Most of these fields are represented as hint buttons, but not all of them.
# To be recognized by the add-on the field html needs to contain text matching the FIELD_HAS_TO_CONTAIN_RE.
# If something is a hint button or not is determined by its presence in the ButtonShortcuts dict.
# The surrounding "<!--" are needed because of the disable field setting.
CONDITIONAL_FIELD_RE = r"(?:<!-- ?)?\{\{#.+?\}\}[\w\W]+?\{\{/.+?\}\}(?: ?-->)?"
CONFIGURABLE_FIELD_HAS_TO_CONTAIN_RE = r'(class="hints"|id="extra")'
CONFIGURABLE_FIELD_NAME_RE = r"\{\{#(.+?)\}\}"


# for matching text between double quotes which can contain escaped quotes
QUOT_STR_RE = r'(?:\\.|[^"\\])'


HINT_BUTTONS = {
    "zusatz": "Eigene Notizen und Bilder",
    "hammer": "Prüfungsfragen",
    "klinik": "Klinik",
    "image": "Bild",
    "amboss": "AMBOSS",
    "thieme": "Thieme",
    "meditricks": "Meditricks",
}

ANKIMOBILE_USER_ACTIONS = [
    "undefined",
    "window.revealNextCloze",
    "window.toggleAllCloze",
    "() => revealNextClozeOf('Wort')",
    "window.toggleNextButton",
    "() => (Array.from(document.getElementsByClassName('hintBtn')).forEach(e => toggleHintBtn(e.id)))",
    "window.toggleNext",
    "window.toggleAll",
    "window.showtags",
    *[f"() => toggleHintBtn('hint-{id}')" for id in HINT_BUTTONS.keys()],
]
ANKIMOBILE_USER_ACTION_LABELS = [
    "Keine Aktion",
    "Nächste Lücke aufdecken",
    "Alle Lücken aufdecken",
    "Decke nächstes Wort auf",
    "Nächsten Button aufdecken",
    "Alle Buttons aufdecken",
    "Nächste Image Occlusion aufdecken",
    "Alle Image Occlusions aufdecken",
    "Schlagwörter anzeigen",
    *[f"Decke {name} auf" for name in HINT_BUTTONS.values()],
]


setting_configs: Dict[str, Any] = OrderedDict(
    {
        "field_order": {
            "text": "Feld-Reihenfolge",
            "tooltip": "Zieh die Felder in die gewünschte Reihenfolge.",
            "type": "order",
            "file": "back",
            "regex": r"[\w\W]*",
            "elem_re": CONDITIONAL_FIELD_RE,
            "name_re": CONFIGURABLE_FIELD_NAME_RE,
            "has_to_contain": CONFIGURABLE_FIELD_HAS_TO_CONTAIN_RE,
            "section": "Felder",
        },
        "toggle_next_button": {
            "text": "Nächsten Button aufdecken - Tastenkürzel",
            "tooltip": "",
            "type": "shortcut",
            "file": "back",
            "regex": rf'var +ToggleNextButtonShortcut += +"({QUOT_STR_RE}*?)"',
            "section": "Zusatz Buttons",
            "default": "H",
        },
        "toggle_all_buttons": {
            "text": "Alle Buttons aufdecken - Tastenkürzel",
            "tooltip": "",
            "type": "shortcut",
            "file": "back",
            "regex": rf'var +ToggleAllButtonsShortcut += +"({QUOT_STR_RE}*?)"',
            "section": "Zusatz Buttons",
            "default": "'",
        },
        "autoscroll_to_button": {
            "text": "Automatisch zum Button scrollen",
            "tooltip": "",
            "type": "checkbox",
            "file": "back",
            "regex": r"var +ScrollToButton += +(false|true)",
            "section": "Zusatz Buttons",
            "default": True,
        },
        "autoscroll_to_hint": {
            "text": "Automatisch zum Hinweis scrollen",
            "tooltip": "",
            "type": "checkbox",
            "file": "back",
            "regex": r"var +ScrollToHint += +(false|true)",
            "section": "Zusatz Buttons",
            "default": True,
        },
        "io_reveal_next_shortcut": {
            "text": "Nächste Image Occlusion aufdecken - Tastenkürzel",
            "tooltip": "",
            "type": "shortcut",
            "file": "back",
            "regex": rf'var +RevealIncrementalShortcut += +"({QUOT_STR_RE}*?)"',
            "section": "Image Occlusion",
            "default": "N",
        },
        "io_toggle_all_shortcut": {
            "text": "Alle Image Occlusions aufdecken - Tastenkürzel",
            "tooltip": "",
            "type": "shortcut",
            "file": "back",
            "regex": rf'var +ToggleAllOcclusionsShortcut += +"({QUOT_STR_RE}*?)"',
            "section": "Image Occlusion",
            "default": ",",
        },
        "reveal_cloze_shortcut": {
            "text": "Lücke aufdecken - Tastenkürzel",
            "tooltip": "",
            "type": "shortcut",
            "file": "back",
            "regex": rf'var +revealNextShortcut += +"({QUOT_STR_RE}*?)"',
            "section": "Lücken",
            "default": "N",
        },
        "reveal_cloze_word_shortcut": {
            "text": "Lücke Wort für Wort aufdecken - Tastenkürzel",
            "tooltip": "",
            "type": "shortcut",
            "file": "back",
            "regex": rf'var +revealNextWordShortcut += +"({QUOT_STR_RE}*?)"',
            "section": "Lücken",
            "default": "Shift+N",
        },
        "toggle_all_clozes_shortcut": {
            "text": "Alle Lücken aufdecken - Tastenkürzel",
            "tooltip": "",
            "type": "shortcut",
            "file": "back",
            "regex": rf'var +toggleAllShortcut += +"({QUOT_STR_RE}*?)"',
            "section": "Lücken",
            "default": ",",
        },
        "reveal_next_cloze_mode": {
            "text": "Aufdeckmodus",
            "tooltip": "cloze: Lücken normal aufdecken\nword: Lücken Wort für Wort aufdecken",
            "type": "dropdown",
            "file": "back",
            "regex": r'var +revealNextClozeMode += +"([^"]*?)"',
            "options": ["cloze", "word"],
            "section": "Lücken",
            "default": "cloze",
        },
        "cloze_hider": {
            "text": "Lückenverdecker",
            "tooltip": "Text, der die Lücke verdeckt",
            "type": "text",
            "file": "back",
            "regex": rf'var +clozeHider +=[^"]+"({QUOT_STR_RE}*?)"',
            "section": "Lücken",
            "default": "👑",
        },
        "timer": {
            "text": "Countdown",
            "tooltip": "",
            "type": "re_checkbox",
            "file": "style",
            "regex": r"\.timer *{[^}]*?display: (block|none);",
            "replacement_pairs": [("none", "block")],
            "section": "Countdown",
            "default": True,
        },
        "timer_secs": {
            "text": "Countdown Dauer (Sekunden)",
            "tooltip": "",
            "type": "number",
            "file": "front",
            "regex": r"var +seconds += +([^ /\n]*)",
            "min": 0,
            "section": "Countdown",
            "default": 9,
        },
        "timer_minutes": {
            "text": "Countdown Dauer (Minuten)",
            "tooltip": "",
            "type": "number",
            "file": "front",
            "regex": r"var +minutes += +([^ /\n]*)",
            "min": 0,
            "section": "Countdown",
            "default": 0,
        },
        "autoflip": {
            "text": "Kartenrückseite automatisch aufdecken\n(funktioniert nicht auf AnkiMobile)",
            "tooltip": "",
            "type": "checkbox",
            "file": "front",
            "regex": r"var +autoflip += +(false|true)",
            "default": True,
        },
        "front_two_columns": {
            "text": "2-Spalten-Layout auf der Vorderseite verwenden",
            "tooltip": "",
            "type": "checkbox",
            "file": "front",
            "regex": r"var +twoColumnLayout += +(false|true)",
            "section": "Layout",
            "default": False,
        },
        "front_column_ratio": {
            "text": "Verhältnis der 2 Spalten auf der Vorderseite",
            "tooltip": "",
            "type": "text",
            "file": "front",
            "regex": rf'var +columnRatio += +"({QUOT_STR_RE}*?)"',
            "section": "Layout",
            "default": "1fr 1.5fr",
        },
        "back_two_columns": {
            "text": "2-Spalten-Layout auf der Rückseite verwenden",
            "tooltip": "",
            "type": "checkbox",
            "file": "back",
            "regex": r"var +twoColumnLayout += +(false|true)",
            "section": "Layout",
            "default": False,
        },
        "back_column_ratio": {
            "text": "Verhältnis der 2 Spalten auf der Rückseite",
            "tooltip": "",
            "type": "text",
            "file": "back",
            "regex": rf'var +columnRatio += +"({QUOT_STR_RE}*?)"',
            "section": "Layout",
            "default": "1fr 1.5fr",
        },
        "front_tts": {
            "text": "Front TTS",
            "tooltip": "",
            "type": "re_checkbox",
            "file": "front",
            "regex": r"(<!--|{{)tts.+?(-->|}})",
            "replacement_pairs": [("<!--", "{{"), ("-->", "}}")],
            "section": "Text to Speech",
            "default": False,
        },
        "front_tts_speed": {
            "text": "Front TTS Speed",
            "tooltip": "",
            "type": "number",
            "decimal": True,
            "min": 0.1,
            "max": 10,
            "step": 0.1,
            "file": "front",
            "regex": r"(?:<!--|{{)tts.*?speed=([\d\.]+).*?(?:-->|}})",
            "section": "Text to Speech",
            "default": 1.4,
        },
        "back_tts": {
            "text": "Back TTS",
            "tooltip": """if you enable this and want to use the shortcut for revealing hint buttons one by one
you may have to change the \"Toggle next Button\" shortcut to something else than "H"
(it is in the Hint Buttons section)""",
            "type": "re_checkbox",
            "file": "back",
            "regex": r"(<!--|{{)tts.+?(-->|}})",
            "replacement_pairs": [("<!--", "{{"), ("-->", "}}")],
            "section": "Text to Speech",
            "default": False,
        },
        "back_tts_speed": {
            "text": "Back TTS Speed",
            "tooltip": "",
            "type": "number",
            "decimal": True,
            "min": 0.1,
            "max": 10,
            "step": 0.1,
            "file": "back",
            "regex": r"(?:<!--|{{)tts.*?speed=([\d\.]+).*?(?:-->|}})",
            "section": "Text to Speech",
            "default": 1.4,
        },
        "front_signal_tag": {
            "text": "Schlagwort, das die Vorderseite rot färbt",
            "tooltip": "",
            "type": "text",
            "file": "front",
            "regex": rf'var +tagID += +"({QUOT_STR_RE}*?)"',
            "section": "Tags",
            "default": "XXXYYYZZZ",
        },
        "back_signal_tag": {
            "text": "Schlagwort, das die Rückseite rot färbt",
            "tooltip": "",
            "type": "text",
            "file": "back",
            "regex": rf'var +tagID += +"({QUOT_STR_RE}*?)"',
            "section": "Tags",
            "default": "XXXYYYZZZ",
        },
        "university_tag": {
            "text": "Universität, die in den Tags nicht ausgeblendet werden soll",
            "tooltip": "",
            "type": "text",
            "file": "back",
            "regex": rf'var +tagUniversity += +"({QUOT_STR_RE}*?)"',
            "section": "Tags",
            "default": "XXXYYYZZZ",
        },
        "tags_container": {
            "text": "Tags container",
            "tooltip": "",
            "type": "re_checkbox",
            "file": "style",
            "regex": r"\n#tags-container *{[^}]*?display: (block|none);",
            "replacement_pairs": [("none", "block")],
            "section": "Tags",
            "default": True,
        },
        "tags_container_mobile": {
            "text": "Tags container (mobile)",
            "tooltip": "",
            "type": "re_checkbox",
            "file": "style",
            "regex": r"\.mobile +#tags-container *{[^}]*?display: (block|none);",
            "replacement_pairs": [("none", "block")],
            "section": "Tags",
            "default": False,
        },
        "tags_toggle_shortcut": {
            "text": "Schlagwort-Tastenkürzel",
            "tooltip": "",
            "type": "shortcut",
            "file": "back",
            "regex": rf'var +toggleTagsShortcut += +"({QUOT_STR_RE}*?)"',
            "section": "Tags",
            "default": "C",
        },
        "tags_num_levels_to_show_front": {
            "text": "Schlagwortebenen auf Vorderseite anzeigen (0 bedeutet alle)",
            "type": "number",
            "file": "front",
            "regex": r"var +numTagLevelsToShow += +(\d+)",
            "section": "Tags",
            "default": 0,
        },
        "tags_num_levels_to_show_back": {
            "text": "Schlagwortebenen auf Rückseite anzeigen (0 bedeutet alle)",
            "type": "number",
            "file": "back",
            "regex": r"var +numTagLevelsToShow += +(\d+)",
            "section": "Tags",
            "default": 0,
        },
        "font_size": {
            "text": "Schriftgröße",
            "tooltip": "",
            "type": "number",
            "file": "style",
            "regex": r"html *{[^}]*?font-size: (\d+)px;",
            "min": 1,
            "max": 200,
            "section": "Schriftart",
            "default": 20,
        },
        "font_size_mobile": {
            "text": "Schriftgröße (Mobil)",
            "tooltip": "",
            "type": "number",
            "file": "style",
            "regex": r"\.mobile *{[^}]*?font-size: ([\d]+)px;",
            "min": 1,
            "max": 200,
            "section": "Schriftart",
            "default": 20,
        },
        "font_family": {
            "text": "Schriftart",
            "tooltip": "",
            "type": "font_family",
            "file": "style",
            "regex": r"\.card.*\n*kbd *{[^}]*?font-family: (.+);",
            "section": "Schriftart",
            "default": "Arial Greek, Arial",
        },
        "text_align": {
            "text": "Standard-Textausrichtung",
            "tooltip": "left: Text links ausrichten\ncenter: Text mittig ausrichten",
            "type": "dropdown",
            "file": "style",
            "regex": r"--default-alignment: (.+?);",
            "options": ["left", "center"],
            "section": "Layout",
            "default": "left",
        },
        "button_align": {
            "text": "Standard-Knopfausrichtung",
            "tooltip": "left: Knöpfe links ausrichten\ncenter: Knöpfe mittig ausrichten",
            "type": "dropdown",
            "file": "style",
            "regex": r"--button-alignment: (.+?);",
            "options": ["left", "center"],
            "section": "Layout",
            "default": "center",
        },
        "image_height": {
            "text": "Maximale Bildhöhe in Prozent",
            "tooltip": "",
            "type": "number",
            "file": "style",
            "regex": r"\nimg *{[^}]*?max-height: (.+)%;",
            "max": 100,
            "section": "Bilder",
            "default": 100,
        },
        "image_width": {
            "text": "Maximale Bildbreite in Prozent",
            "tooltip": "",
            "type": "number",
            "file": "style",
            "regex": r"\nimg *{[^}]*?max-width: (.+)%;",
            "max": 100,
            "section": "Bilder",
            "default": 85,
        },
        "text_color": {
            "text": "Standard-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--text: (.+?);",
            "section": "Farben",
            "default": "#363638",
        },
        "background_color": {
            "text": "Hintergrundfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--bg: (.+?);",
            "section": "Farben",
            "default": "#f8f8f8",
        },
        "cloze_color": {
            "text": "Cloze-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--text-cloze: (.+?);",
            "section": "Farben",
            "default": "IndianRed",
        },
        "extra_text_color": {
            "text": "Extra-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"#extra *{[^}]*?color: (.+?);",
            "section": "Farben",
            "default": "navy",
        },
        "hint_text_color": {
            "text": "Hinweis-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"\.hints *{[^}]*?color: (.+?);",
            "section": "Farben",
            "default": "#4297F9",
        },
        "missed_text_color": {
            "text": "Fehlgeschlagen Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"#missed *{[^}]*?color: (.+?);",
            "section": "Farben",
            "default": "red",
        },
        "timer_text_color": {
            "text": "Timer Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"\.timer *{[^}]*?color: (.+?);",
            "section": "Farben",
            "default": "transparent",
        },
        "nm_text_color": {
            "text": "Dunkelmodus Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--nm-text: (.+?)( +!important)?;",
            "section": "Farben",
            "default": "#e9e9e9",
        },
        "nm_background_color": {
            "text": "Dunkelmodus Hintergrundfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--nm-bg: (.+?)( +!important)?;",
            "section": "Farben",
            "default": "#363638",
        },
        "nm_cloze_color": {
            "text": "Dunkelmodus Lückentextfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--text-cloze: (.+?)( +!important)?;",
            "section": "Farben",
            "default": "IndianRed",
        },
        "nm_extra_color": {
            "text": "Dunkelmodus Extra-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"\.night_mode #extra *{[^}]*?color: (.+?)( +!important)?;",
            "section": "Farben",
            "default": "magenta",
        },
        "nm_hint_color": {
            "text": "Dunkelmodus Hinweis-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r".night_mode .hints {[^}]?color: (.+?)( +!important)?;",
            "section": "Farben",
            "default": "cyan",
        },
        "bold_text_color": {
            "text": "Fettgedruckte Textfarbe",
            "tooltip": "auf transparent setzen für normale Farbe",
            "type": "color",
            "file": "style",
            "regex": r"--text-bold: (.+?)( +!important)?;",
            "with_inherit_option": True,
            "section": "Farben",
            "default": "inherit",
        },
        "underlined_text_color": {
            "text": "Unterstrichene Textfarbe",
            "tooltip": "auf transparent setzen für normale Farbe",
            "type": "color",
            "file": "style",
            "regex": r"--text-underline: (.+?)( +!important)?;",
            "with_inherit_option": True,
            "section": "Farben",
            "default": "inherit",
        },
        "italic_text_color": {
            "text": "Schräggestellte Textfarbe",
            "tooltip": "auf transparent setzen für normale Farbe",
            "type": "color",
            "file": "style",
            "regex": r"--text-italics: (.+?)( +!important)?;",
            "with_inherit_option": True,
            "section": "Farben",
            "default": "inherit",
        },
        "image_occlusion_rect_color": {
            "text": "Image Occlusion Rechteck-Füllfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--rect-bg: +([^ ]*?);",
            "section": "Farben",
            "default": "moccasin",
        },
        "image_occlusion_border_color": {
            "text": "Image Occlusion Rechteck-Randfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--rect-border: +([^ ]*?);",
            "section": "Farben",
            "default": "olive",
        },
        "image_occlusion_active_rect_color": {
            "text": "Image Occlusion Rechteck-Füllfarbe - aktiv",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--active-rect-bg: +([^ ]*?);",
            "section": "Farben",
            "default": "salmon",
        },
        "image_occlusion_active_border_color": {
            "text": "Image Occlusion Rechteck-Randfarbe - aktiv",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--active-rect-border: +([^ ]*?);",
            "section": "Farben",
            "default": "yellow",
        },
        "custom_colors": {
            "text": "Custom Farben",
            "tooltip": "Farben, die die Standardfarben ersetzen sollen",
            "type": "text",
            "file": "style",
            "regex": r"\/\*~~~~~~~~~CUSTOM COLOR INSERTION~~~~~~~~~\*\/(\n*?)\n#",
            "section": "ADVANCED",
            "default": "\n",
        },
        "custom_styles": {
            "text": "Custom Styles",
            "tooltip": "Styles, die die Standardfarben ersetzen sollen",
            "type": "text",
            "file": "style",
            "regex": r"\/\*~~~~~~~~~CUSTOM STYLE INSERTION~~~~~~~~~\*\/(\n*?)\n#",
            "section": "ADVANCED",
            "default": "\n",
        },
        **{
            f"user_action_{i}": {
                "text": f"Nutzeraktion {i}",
                "type": "useraction",
                "file": "back",
                "regex": f"var +userJs{i} += +([^/\\n]*)",
                "options": ANKIMOBILE_USER_ACTIONS,
                "labels": ANKIMOBILE_USER_ACTION_LABELS,
                "section": "AnkiMobile Nutzeraktionen",
                "default": "undefined",
            }
            for i in range(1, 9)
        },
    }
)


def projekt_anki_notetype_names():
    return list(projekt_anki_notetype_templates().keys())


def projekt_anki_notetype_templates() -> Dict[str, Tuple[str, str, str]]:
    result = dict()
    for x in PROJEKT_ANKI_NOTETYPES_PATH.iterdir():
        if not x.is_dir():
            continue
        notetype_name = x.name

        front_template = (x / "Front Template.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        back_template = (x / ("Back Template.html")).read_text(
            encoding="utf-8", errors="ignore"
        )
        styling = (x / ("Styling.css")).read_text(encoding="utf-8", errors="ignore")
        result[notetype_name] = (front_template, back_template, styling)

    return result


def projekt_anki_notetype_model(notetype_name: str) -> "NotetypeDict":
    result = json.loads(
        (
            PROJEKT_ANKI_NOTETYPES_PATH / notetype_name / f"{notetype_name}.json"
        ).read_text(encoding="utf-8", errors="ignore")
    )
    front, back, styling = projekt_anki_notetype_templates()[notetype_name]
    result["tmpls"][0]["qfmt"] = front
    result["tmpls"][0]["afmt"] = back
    result["css"] = styling
    return result


def projekt_anki_notetype_models() -> List["NotetypeDict"]:
    return [projekt_anki_notetype_model(name) for name in projekt_anki_notetype_names()]


def all_btns_setting_configs():
    result = OrderedDict()
    for notetype_name in projekt_anki_notetype_templates().keys():
        for field_name in configurable_fields_for_notetype(notetype_name):
            shortcut = btn_name_to_shortcut_odict(notetype_name).get(field_name, None)
            result.update(configurable_field_configs(field_name, shortcut))
    return result


def configurable_fields_for_notetype(notetype_name: str) -> List[str]:
    _, back, _ = projekt_anki_notetype_templates()[notetype_name]

    return [
        re.search(CONFIGURABLE_FIELD_NAME_RE, field).group(1)
        for field in re.findall(CONDITIONAL_FIELD_RE, back)
        if re.search(CONFIGURABLE_FIELD_HAS_TO_CONTAIN_RE, field)
    ]


def btn_name_to_shortcut_odict(notetype_name):
    _, back, _ = projekt_anki_notetype_templates()[notetype_name]

    button_shortcuts_dict_pattern = r"var+ ButtonShortcuts *= *{([^}]*)}"
    m = re.search(button_shortcuts_dict_pattern, back)
    if not m:
        return dict()

    result = OrderedDict()
    dict_key_value_pattern = r'"([^"]+)" *: *"([^"]*)"'
    button_shortcut_pairs = re.findall(dict_key_value_pattern, m.group(1))
    for btn_name, shortcut in button_shortcut_pairs:
        result[btn_name] = shortcut
    return result


def configurable_field_configs(
    name: str, default_shortcut_if_hint_button: Union[str, None]
) -> Dict:
    # if default_shortcut_if_hint_button is None, then this function assumes that
    # the configurable field is not a hint button
    name_in_snake_case = name.lower().replace(" ", "_")
    result = {
        f"disable_{name_in_snake_case}": disable_field_setting_config(name, False),
    }

    if default_shortcut_if_hint_button is not None:
        result.update(
            {
                f"btn_shortcut_{name_in_snake_case}": button_shortcut_setting_config(
                    name, default_shortcut_if_hint_button
                ),
                f"autoreveal_{name_in_snake_case}": button_auto_reveal_setting_config(
                    name, False
                ),
            }
        )

    return result


def button_shortcut_setting_config(field_name: str, default) -> Dict:
    return {
        "text": f"{field_name} Tastenkürzel",
        "type": "shortcut",
        "file": "back",
        "regex": rf'var+ ButtonShortcuts *= *{{[^}}]*?"{field_name}" *: *"({QUOT_STR_RE}*?)"',
        "configurable_field_name": field_name,
        "section": "Zusatz Buttons",
        "default": default,
    }


def button_auto_reveal_setting_config(field_name, default):
    return {
        "text": f"Decke das Feld '{field_name}' automatisch auf",
        "type": "checkbox",
        "file": "back",
        "regex": rf'var+ ButtonAutoReveal *= *{{[^}}]*?"{field_name}" *: *(.+),\n',
        "configurable_field_name": field_name,
        "section": "Zusatz Buttons",
        "default": default,
    }


def disable_field_setting_config(field_name, default):
    return {
        "text": f"{field_name} Feld deaktivieren",
        "tooltip": "",
        "type": "wrap_checkbox",
        "file": "back",
        "regex": rf"(<!--)?{{{{#{field_name}}}}}[\w\W]+?{{{{/{field_name}}}}}(-->)?",
        "wrap_into": ("<!--", "-->"),
        "section": "Felder",
        "default": default,
    }


setting_configs = OrderedDict(**setting_configs, **all_btns_setting_configs())

for setting_name, setting_config in setting_configs.items():
    setting_config["name"] = setting_name

# Settings that apply to multiple note types (the ones that have this setting listed in
# settings_by_notetype).
# They can be overwritten in the note types settings.
general_settings = [
    "toggle_next_button",
    "toggle_all_buttons",
    "autoscroll_to_button",
    "tags_toggle_shortcut",
    "tags_container",
    "tags_container_mobile",
    "reveal_cloze_shortcut",
    "tags_num_levels_to_show_front",
    "tags_num_levels_to_show_back",
    "toggle_all_clozes_shortcut",
    "reveal_next_cloze_mode",
    "cloze_hider",
    "timer",
    "timer_secs",
    "timer_minutes",
    "autoflip",
    "front_two_columns",
    "front_column_ratio",
    "back_two_columns",
    "back_column_ratio",
    "text_align",
    "button_align",
    "front_tts",
    "front_tts_speed",
    "back_tts",
    "back_tts_speed",
    "front_signal_tag",
    "back_signal_tag",
    "university_tag",
    "font_size",
    "font_size_mobile",
    "font_family",
    "image_height",
    "image_width",
    "text_color",
    "background_color",
    "cloze_color",
    "extra_text_color",
    "hint_text_color",
    "missed_text_color",
    "timer_text_color",
    "nm_text_color",
    "nm_background_color",
    "nm_cloze_color",
    "nm_extra_color",
    "nm_hint_color",
    "bold_text_color",
    "underlined_text_color",
    "italic_text_color",
    "image_occlusion_rect_color",
    "image_occlusion_border_color",
    "image_occlusion_active_rect_color",
    "image_occlusion_active_border_color",
    "custom_colors",
    "custom_styles",
    *[f"user_action_{i}" for i in range(1, 9)],
]


def general_settings_defaults_dict():
    result = dict()
    for setting_name in general_settings:
        result[setting_name] = setting_configs[setting_name]["default"]
    return result
