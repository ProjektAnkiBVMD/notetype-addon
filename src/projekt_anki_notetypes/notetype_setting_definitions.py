import json
import re
from pathlib import Path
from typing import Any, Dict, List, OrderedDict, Tuple, Union

try:
    from anki.models import NotetypeDict  # pylint: disable=unused-import
except:
    pass

PROJEKT_ANKI_NOTETYPES_PATH = Path(__file__).parent / "note_types"

FIELD_BOUNDARY_RE = (  # noqa: E731
    lambda ch, field_name_re: rf"(?:\{{\{{{ch}{field_name_re}\}}\}}|<span.+?PSEUDO-FIELD {ch}{field_name_re}</span>)"
)

# Regular expression for fields for which the add-on offers settings aka configurable fields.
# Most of these fields are represented as hint buttons, but not all of them.
# To be recognized by the add-on the field html needs to contain text matching
# CONFIGURABLE_FIELD_HAS_TO_CONTAIN_RE.
# Whether something is a hint button or not is determined by its presence in the ButtonShortcuts dict.
# The surrounding "<!--" are needed because of the disable field setting.
# With the default argument, the regex matches all conditional fields.
CONDITIONAL_FIELD_RE = lambda field_name_re=".+?": (  # noqa: E731
    rf"(?:<!-- ?)?{FIELD_BOUNDARY_RE('#', field_name_re)}[\w\W]+?{FIELD_BOUNDARY_RE('/', field_name_re)}(?: ?-->)?"
)

CONFIGURABLE_FIELD_HAS_TO_CONTAIN_RE = r'(class="hints"|id="extra")'

CONFIGURABLE_FIELD_NAME_RE = r'data-name="([\w\W]+?)"'
CONFIGURABLE_FIELD_FALLBACK_NAME_RE = r"\{\{#(.+?)\}\}"

DO_NOT_DELETE = r"\/\*############ DO NOT DELETE #############\*\/"
DO_NOT_DELETE_HTML = r"<!-- ############ DO NOT DELETE ############# -->"


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
    "() => revealNextClozeOf('word')",
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
            "elem_re": CONDITIONAL_FIELD_RE(),
            "name_res": (
                CONFIGURABLE_FIELD_NAME_RE,
                CONFIGURABLE_FIELD_FALLBACK_NAME_RE,
            ),
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
            "default": "[&nbsp;_&nbsp;]",
        },
        "always_one_by_one": {
            "text": "immer OneByOne (wenn mindestens Mindestanzahl an Clozes)",
            "tooltip": "siehe EXPLANATION.md",
            "type": "checkbox",
            "file": "both",
            "regex": r"var +alwaysOneByOne += +(false|true)",
            "section": "Lücken - erweitert",
            "default": True,
        },
        "selective_one_by_one": {
            "text": "Selektives OneByOne",
            "tooltip": "siehe EXPLANATION.md",
            "type": "checkbox",
            "file": "both",
            "regex": r"var +selectiveOneByOne += +(false|true)",
            "section": "Lücken - erweitert",
            "default": False,
        },
        "min_number_of_clozes_for_one_by_one": {
            "text": "Mindestanzahl an Clozes für OneByOne (wenn 0, dann keine Begrenzung)",
            "tooltip": "siehe EXPLANATION.md",
            "type": "number",
            "file": "both",
            "regex": r"var +minNumberOfClozes += +([^ /\n]*);",
            "min": 0,
            "section": "Lücken - erweitert",
            "default": 3,
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
        "max_card_width": {
            "text": "Maximale Kartenbreite",
            "tooltip": "",
            "type": "text",
            "file": "style",
            "regex": r"--max-card-width: (.+?);",
            "section": "Layout",
            "default": "900px",
        },
        "indenting": {
            "text": "Heuristisches Einrücken verwenden",
            "tooltip": "",
            "type": "checkbox",
            "file": "both",
            "regex": r"var +indentation += +(false|true)",
            "section": "Layout",
            "default": True,
        },
        "bionic_reading": {
            "text": "BionicReading verwenden",
            "tooltip": "",
            "type": "checkbox",
            "file": "both",
            "regex": r"var +bionicReading += +(false|true)",
            "section": "Layout",
            "default": False,
        },
        "divi_format": {
            "text": "Medikationen nach DIVI-Standard formatieren",
            "tooltip": "",
            "type": "checkbox",
            "file": "both",
            "regex": r"var +formattingDIVI += +(false|true)",
            "section": "Layout",
            "default": False,
        },
        "two_columns": {
            "text": "2-Spalten-Layout verwenden",
            "tooltip": "",
            "type": "checkbox",
            "file": "both",
            "regex": r"var +twoColumnLayout += +(false|true)",
            "section": "Layout",
            "default": False,
        },
        "column_ratio": {
            "text": "Verhältnis der 2 Spalten",
            "tooltip": "",
            "type": "text",
            "file": "both",
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
            "tooltip": (
                "if you enable this and want to use the shortcut for revealing "
                'hint buttons one by one you may have to change the "Toggle '
                'next Button" shortcut to something else than "H" (it is in '
                "the Hint Buttons section)"
            ),
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
            "file": "both",
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
        "tags_num_levels_to_show": {
            "text": "Schlagwortebenen, die angezeigt werden sollen (0 bedeutet alle)",
            "type": "number",
            "file": "both",
            "regex": r"var +numTagLevelsToShow += +(\d+)",
            "section": "Tags",
            "default": 0,
        },
        "font_size": {
            "text": "Schriftgröße",
            "tooltip": "",
            "type": "text",
            "file": "style",
            "regex": r"--text-font-size: (.+?);",
            "section": "Schriftart",
            "default": "22px",
        },
        "font_size_extra": {
            "text": "Schriftgröße (Extra und andere Felder)",
            "tooltip": "",
            "type": "text",
            "file": "style",
            "regex": r"--extra-font-size: (.+?);",
            "section": "Schriftart",
            "default": "18px",
        },
        "font_size_table": {
            "text": "Schriftgröße (Tabellen)",
            "tooltip": "",
            "type": "text",
            "file": "style",
            "regex": r"--table-font-size: (.+?);",
            "section": "Schriftart",
            "default": "1em",
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
        "content_align": {
            "text": "Standard-Hauptinhaltsausrichtung",
            "tooltip": "left: Hauptinhalt links ausrichten\ncenter: Hauptinhalt mittig ausrichten",
            "type": "dropdown",
            "file": "style",
            "regex": r"--content-alignment: (.+?);",
            "options": ["left", "center"],
            "section": "Layout",
            "default": "left",
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
        "image_brightness": {
            "text": "Bild-Helligkeit (Nachtmodus)",
            "tooltip": "",
            "type": "text",
            "file": "style",
            "regex": r"--nm-brightness: (.+?);",
            "section": "Bilder",
            "default": "0.8",
        },
        "text_color": {
            "text": "A - Light-Mode: Standard-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--text: (.+?);",
            "section": "Farben",
            "default": "#363638",
        },
        "background_color": {
            "text": "A - Light-Mode: Hintergrundfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--bg: (.+?);",
            "section": "Farben",
            "default": "#f8f8f8",
        },
        "bold_text_color": {
            "text": "A - Light-Mode: Fettgedruckte Textfarbe",
            "tooltip": "auf transparent setzen für normale Farbe",
            "type": "color",
            "file": "style",
            "regex": r"--text-bold: (.+?)( +!important)?;",
            "with_inherit_option": True,
            "section": "Farben",
            "default": "inherit",
        },
        "underlined_text_color": {
            "text": "A - Light-Mode: Unterstrichene Textfarbe",
            "tooltip": "auf transparent setzen für normale Farbe",
            "type": "color",
            "file": "style",
            "regex": r"--text-underline: (.+?)( +!important)?;",
            "with_inherit_option": True,
            "section": "Farben",
            "default": "inherit",
        },
        "italic_text_color": {
            "text": "A - Light-Mode: Schräggestellte Textfarbe",
            "tooltip": "auf transparent setzen für normale Farbe",
            "type": "color",
            "file": "style",
            "regex": r"--text-italics: (.+?)( +!important)?;",
            "with_inherit_option": True,
            "section": "Farben",
            "default": "inherit",
        },
        "cloze_color": {
            "text": "A - Light-Mode: Cloze-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--text-cloze: (.+?);",
            "section": "Farben",
            "default": "IndianRed",
        },
        "question_color": {
            "text": "A - Light-Mode: Fragen-Textfarbe",
            "tooltip": "Für 'Blickdiagnose?' und Muskel / Leitungsbahnen im AnatomieTrainer",
            "type": "color",
            "file": "style",
            "regex": r"--text-frage: (.+?);",
            "section": "Farben",
            "default": "rebeccapurple",
        },
        "extra_text_color": {
            "text": "A - Light-Mode: Extra-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"#extra *{[^}]*?color: (.+?);",
            "section": "Farben",
            "default": "navy",
        },
        "hint_text_color": {
            "text": "A - Light-Mode: Hinweis-Textfarbe",
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
            "text": "B - Dark-Mode: Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--nm-text: (.+?)( +!important)?;",
            "section": "Farben",
            "default": "#e9e9e9",
        },
        "nm_background_color": {
            "text": "B - Dark-Mode: Hintergrundfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--nm-bg: (.+?)( +!important)?;",
            "section": "Farben",
            "default": "#363638",
        },
        "nm_bold_text_color": {
            "text": "B - Dark-Mode: Fettgedruckte Textfarbe",
            "tooltip": "auf transparent setzen für normale Farbe",
            "type": "color",
            "file": "style",
            "regex": r"--nm-text-bold: (.+?)( +!important)?;",
            "with_inherit_option": True,
            "section": "Farben",
            "default": "inherit",
        },
        "nm_underlined_text_color": {
            "text": "B - Dark-Mode: Unterstrichene Textfarbe",
            "tooltip": "auf transparent setzen für normale Farbe",
            "type": "color",
            "file": "style",
            "regex": r"--nm-text-underline: (.+?)( +!important)?;",
            "with_inherit_option": True,
            "section": "Farben",
            "default": "inherit",
        },
        "nm_italic_text_color": {
            "text": "B - Dark-Mode: Schräggestellte Textfarbe",
            "tooltip": "auf transparent setzen für normale Farbe",
            "type": "color",
            "file": "style",
            "regex": r"-nm-text-italics: (.+?)( +!important)?;",
            "with_inherit_option": True,
            "section": "Farben",
            "default": "inherit",
        },
        "nm_cloze_color": {
            "text": "B - Dark-Mode: Lückentextfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--nm-text-cloze: (.+?)( +!important)?;",
            "section": "Farben",
            "default": "IndianRed",
        },
        "nm_question_color": {
            "text": "B - Dark-Mode: Fragen-Textfarbe",
            "tooltip": "Für 'Blickdiagnose?' und Muskel / Leitungsbahnen im AnatomieTrainer",
            "type": "color",
            "file": "style",
            "regex": r"--nm-text-frage: (.+?);",
            "section": "Farben",
            "default": "#9381FF",
        },
        "nm_extra_color": {
            "text": "B - Dark-Mode: Extra-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"\.night_mode #extra *{[^}]*?color: (.+?)( +!important)?;",
            "section": "Farben",
            "default": "magenta",
        },
        "nm_hint_color": {
            "text": "B - Dark-Mode: Hinweis-Textfarbe",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"\.night_mode \.hints {[^}]?color: (.+?)( +!important)?;",
            "section": "Farben",
            "default": "cyan",
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
        "image_occlusion_highlight_border_color": {
            "text": "Image Occlusion Rechteck-Füllfarbe - nächste Occlusion",
            "tooltip": "",
            "type": "color",
            "file": "style",
            "regex": r"--highlight-rect-bg: +([^ ]*?);",
            "section": "Farben",
            "default": "#00FF00",
        },
        "custom_colors": {
            "text": "Custom Farben",
            "tooltip": "Farben, die die Standardfarben ersetzen sollen",
            "type": "text",
            "file": "style",
            "regex": rf"{DO_NOT_DELETE}\n\/\*~~~~~~~~~CUSTOM COLOR INSERTION~~~~~~~~~\*\/\n(((.|\n)*?))\n{DO_NOT_DELETE}",
            "section": "ADVANCED",
            "default": "\n",
        },
        "custom_styles": {
            "text": "Custom Styles",
            "tooltip": "Styles, die die Standardfarben ersetzen sollen",
            "type": "text",
            "file": "style",
            "regex": rf"{DO_NOT_DELETE}\n\/\*~~~~~~~~~CUSTOM STYLE INSERTION~~~~~~~~~\*\/\n(((.|\n)*?))\n{DO_NOT_DELETE}",
            "section": "ADVANCED",
            "default": "\n",
        },
        "custom_scripts_front": {
            "text": "Custom Scripts (Front)",
            "tooltip": "Scripts, die zusätzlich zu den Standardscripts eingefügt werden sollen",
            "type": "text",
            "file": "front",
            "regex": rf"{DO_NOT_DELETE_HTML}\n<!-- ~~~~~~~~~CUSTOM SCRIPT INSERTION~~~~~~~~ -->\n(((.|\n)*?))\n{DO_NOT_DELETE_HTML}",
            "section": "ADVANCED",
            "default": "\n",
        },
        "custom_scripts_back": {
            "text": "Custom Scripts (Back)",
            "tooltip": "Scripts, die zusätzlich zu den Standardscripts eingefügt werden sollen",
            "type": "text",
            "file": "back",
            "regex": rf"{DO_NOT_DELETE_HTML}\n<!-- ~~~~~~~~~CUSTOM SCRIPT INSERTION~~~~~~~~ -->\n(((.|\n)*?))\n{DO_NOT_DELETE_HTML}",
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
        styling = (x / ("Styling.css")).read_text(
            encoding="utf-8", errors="ignore"
        )
        result[notetype_name] = (front_template, back_template, styling)

    return result


def projekt_anki_notetype_model(notetype_name: str) -> "NotetypeDict":
    result = json.loads(
        (
            PROJEKT_ANKI_NOTETYPES_PATH
            / notetype_name
            / f"{notetype_name}.json"
        ).read_text(encoding="utf-8", errors="ignore")
    )
    front, back, styling = projekt_anki_notetype_templates()[notetype_name]
    result["tmpls"][0]["qfmt"] = front
    result["tmpls"][0]["afmt"] = back
    result["css"] = styling
    return result


def projekt_anki_notetype_models() -> List["NotetypeDict"]:
    return [
        projekt_anki_notetype_model(name)
        for name in projekt_anki_notetype_names()
    ]


def all_btns_setting_configs():
    result = OrderedDict()
    for notetype_name in projekt_anki_notetype_templates().keys():
        fields = configurable_fields_for_notetype(notetype_name)
        for field_name in fields:
            shortcut = btn_name_to_shortcut_odict(notetype_name).get(
                field_name, None
            )
            result.update(configurable_field_configs(field_name, shortcut))
    return result


def configurable_fields_for_notetype(notetype_name: str) -> List[str]:
    _, back, _ = projekt_anki_notetype_templates()[notetype_name]

    result = []
    for field in re.findall(CONDITIONAL_FIELD_RE(), back):
        if not re.search(CONFIGURABLE_FIELD_HAS_TO_CONTAIN_RE, field):
            continue

        name_patterns = [
            CONFIGURABLE_FIELD_NAME_RE,
            CONFIGURABLE_FIELD_FALLBACK_NAME_RE,
        ]
        for pattern in name_patterns:
            m = re.search(pattern, field)
            if m:
                result.append(m.group(1))
                break

    return result


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
        f"disable_{name_in_snake_case}": disable_field_setting_config(
            name, False
        ),
    }

    if default_shortcut_if_hint_button is not None:
        result.update(
            {
                f"btn_shortcut_{name_in_snake_case}": (
                    button_shortcut_setting_config(
                        name, default_shortcut_if_hint_button
                    )
                ),
                f"autoreveal_{name_in_snake_case}": (
                    button_auto_reveal_setting_config(name, False)
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
        "regex": CONDITIONAL_FIELD_RE(field_name),
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
    "tags_num_levels_to_show",
    "toggle_all_clozes_shortcut",
    "reveal_next_cloze_mode",
    "cloze_hider",
    "always_one_by_one",
    "selective_one_by_one",
    "min_number_of_clozes_for_one_by_one",
    "timer",
    "timer_secs",
    "timer_minutes",
    "autoflip",
    "max_card_width",
    "indenting",
    "bionic_reading",
    "divi_format",
    "two_columns",
    "column_ratio",
    "text_align",
    "button_align",
    "content_align",
    "front_tts",
    "front_tts_speed",
    "back_tts",
    "back_tts_speed",
    "front_signal_tag",
    "back_signal_tag",
    "university_tag",
    "font_size",
    "font_size_extra",
    "font_size_table",
    "font_family",
    "image_height",
    "image_width",
    "image_brightness",
    "text_color",
    "background_color",
    "bold_text_color",
    "underlined_text_color",
    "italic_text_color",
    "cloze_color",
    "question_color",
    "extra_text_color",
    "hint_text_color",
    "missed_text_color",
    "timer_text_color",
    "nm_text_color",
    "nm_background_color",
    "nm_bold_text_color",
    "nm_underlined_text_color",
    "nm_italic_text_color",
    "nm_cloze_color",
    "nm_question_color",
    "nm_extra_color",
    "nm_hint_color",
    "image_occlusion_rect_color",
    "image_occlusion_border_color",
    "image_occlusion_active_rect_color",
    "image_occlusion_active_border_color",
    "image_occlusion_highlight_border_color",
    "custom_colors",
    "custom_styles",
    "custom_scripts_front",
    "custom_scripts_back",
    *[f"user_action_{i}" for i in range(1, 9)],
]


def general_settings_defaults_dict():
    result = dict()
    for setting_name in general_settings:
        result[setting_name] = setting_configs[setting_name]["default"]
    return result
