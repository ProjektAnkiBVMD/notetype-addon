import re
from collections import defaultdict
from concurrent.futures import Future
from typing import Any, Dict, List, Optional, Union

from aqt import mw
from aqt.clayout import CardLayout
from aqt.qt import QWidget
from aqt.utils import askUser, showInfo, tooltip

from ..ankiaddonconfig import ConfigManager, ConfigWindow
from ..ankiaddonconfig.window import ConfigLayout
from ..constants import ANKIHUB_NOTETYPE_RE, NOTETYPE_COPY_RE
from ..notetype_setting import NotetypeSetting, NotetypeSettingException
from ..notetype_setting_definitions import (
    projekt_anki_notetype_model,
    projekt_anki_notetype_names,
    configurable_fields_for_notetype,
    general_settings,
    general_settings_defaults_dict,
    setting_configs,
)
from ..utils import update_notetype_to_newest_version
from .projekt_anki_widgets import AnkingIconsLayout, GithubLinkLayout
from .extra_notetype_versions import handle_extra_notetype_versions

try:
    from anki.models import NotetypeDict  # pylint: disable=unused-import
except:
    pass


def ntss_for_model(model: "NotetypeDict") -> List[NotetypeSetting]:
    # returns all nts that are present on the notetype
    result = []
    for setting_config in setting_configs.values():
        nts = NotetypeSetting.from_config(setting_config)
        if nts.is_present(model):
            result.append(nts)

    return result


def general_ntss() -> List[NotetypeSetting]:
    result = []
    for setting_name in general_settings:
        result.append(NotetypeSetting.from_config(setting_configs[setting_name]))
    return result


class NotetypesConfigWindow:
    window: Optional[ConfigWindow] = None

    def __init__(self, clayout_: CardLayout = None):
        # code in this class assumes that if bool(clayout) is true, clayout.model contains
        # an anking notetype model
        self.clayout = None
        if clayout_:
            if clayout_.model["name"] in _names_of_all_supported_note_types():
                self.clayout = clayout_

        self.conf = None
        self.last_general_ntss: Union[List[NotetypeSetting], None] = None

    def open(self):
        handle_extra_notetype_versions()

        # dont open another window if one is already open
        if self.__class__.window:
            is_open = True
            # when the window is closed c++ deletes the qdialog and calling methods
            # of the window fails with a RuntimeError
            try:
                self.window.isVisible()
            except RuntimeError:
                is_open = False

            if is_open:
                self.window.activateWindow()
                self.window.raise_()
                return

        # ankiaddonconfig's ConfigManager is used here in a way that is not intended
        # the save functionality gets overwritten and nothing gets saved to the Anki
        # addon config
        # the config is populated at the start with the current setting values parsed
        # from the notetype and then used to update the settings
        self.conf = ConfigManager()

        self._read_in_settings()

        # add general tab
        self.conf.add_config_tab(lambda window: self._add_general_tab(window))

        # setup tabs for all notetypes
        for notetype_base_name in sorted(projekt_anki_notetype_names()):
            self.conf.add_config_tab(
                lambda window, notetype_base_name=notetype_base_name: self._add_notetype_settings_tab(
                    notetype_base_name=notetype_base_name, window=window
                )
            )

        # setup live update of clayout model on changes
        def live_update_clayout_model(key: str, _: Any):
            notetype_base_name_from_setting, setting_name = key.split(".")
            model = self.clayout.model
            notetype_base_name_from_model = _notetype_base_name(model["name"])
            if notetype_base_name_from_setting != notetype_base_name_from_model:
                return

            nts = NotetypeSetting.from_config(setting_configs[setting_name])
            self._safe_update_model_settings(
                model=model,
                notetype_base_name=notetype_base_name_from_model,
                ntss=[nts],
            )

            self._update_clayout_model(model)

        if self.clayout:
            self.conf.on_change(live_update_clayout_model)

        # change window settings, overwrite on_save, setup notetype updates
        self.conf.on_window_open(self._setup_window_settings)

        # open the config window
        if self.clayout:
            self.conf.open_config(self.clayout)
        else:
            self.conf.open_config()

    def _setup_window_settings(self, window: ConfigWindow):
        self.__class__.window = window
        window.setWindowTitle("Projekt Anki Notiztypen")
        window.setMinimumHeight(500)
        window.setMinimumWidth(500)

        # overwrite on_save function
        def on_save(window: ConfigWindow):
            self._apply_setting_changes_for_all_notetypes()
            window.close()

        window.save_btn.clicked.disconnect()  # type: ignore
        window.save_btn.clicked.connect(lambda: on_save(window))  # type: ignore

        if self.clayout:
            self._set_active_tab(_notetype_base_name(self.clayout.model["name"]))

        # add anking links layouts
        widget = QWidget()
        window.main_layout.insertWidget(0, widget)
        AnkingIconsLayout(widget)

        widget = QWidget()
        window.main_layout.addWidget(widget)
        GithubLinkLayout(
            widget, href="https://github.com/ProjektAnki/notetype-addon/issues"
        )

    # tabs and NotetypeSettings (ntss)
    def _add_notetype_settings_tab(
        self,
        notetype_base_name: str,
        window: ConfigWindow,
        index: Optional[int] = None,
    ):
        if (
            self.clayout
            and _notetype_base_name(self.clayout.model["name"]) == notetype_base_name
        ):
            model = self.clayout.model
        else:
            model = _most_basic_notetype_version(notetype_base_name)

        tab = window.add_tab(notetype_base_name, index=index)

        if model:
            ntss = ntss_for_model(model)
            ordered_ntss = self._adjust_configurable_field_nts_order(
                ntss=ntss, notetype_base_name=notetype_base_name
            )
            scroll = tab.scroll_layout()
            self._add_nts_widgets_to_layout(scroll, ordered_ntss, model)
            scroll.stretch()

            layout = tab.hlayout()
            layout.button(
                "Zurücksetzen",
                on_click=lambda: self._reset_notetype_and_reload_ui(model),
            )
            layout.stretch()
        else:
            tab.text("Dieser Notiztyp ist nicht in deiner Collection.")
            tab.stretch()

            tab.button(
                "Importieren",
                on_click=lambda: self._import_notetype_and_reload_tab(
                    notetype_base_name
                ),
            )

    def _add_general_tab(self, window: ConfigWindow):
        tab = window.add_tab("Allgemein", index=0)

        prev_ntss = self.last_general_ntss
        self.last_general_ntss = ntss = general_ntss()

        scroll = tab.scroll_layout()
        self._add_nts_widgets_to_layout(scroll, ntss, None, general=True)
        scroll.stretch()

        if prev_ntss:
            for nts in prev_ntss:
                nts.unregister_general_setting(tab.conf)

        for nts in ntss:
            nts.register_general_setting(tab.conf)

        tab.space(10)
        tab.text(
            "Änderungen hier betreffen alle Notiztypen, die diese Einstellung haben.",
            bold=True,
            multiline=True,
        )
        tab.space(10)

        update_btn = tab.button(
            "Aktualisiere Notiztypen",
            on_click=self._update_all_notetypes_to_newest_version_and_reload_ui,
        )

        reset_btn = tab.button(
            "Setze alle Notiztypen zurück",
            on_click=self._reset_all_notetypes_and_reload_ui,
        )

        if models_with_available_updates():
            tab.text("Es gibt Updates für die Notiztypen!")
        else:
            update_btn.setDisabled(True)

    def _add_nts_widgets_to_layout(
        self,
        layout: ConfigLayout,
        ntss: List[NotetypeSetting],
        model: "NotetypeDict",
        general=False,
    ) -> None:
        if general:
            assert model is None

        nts_to_section = {
            nts: section_name
            for nts in ntss
            if (section_name := nts.config.get("section", None))
        }

        section_to_ntss: Dict[str, List[NotetypeSetting]] = defaultdict(lambda: [])
        for nts, section in nts_to_section.items():
            section_to_ntss[section].append(nts)

        notetype_base_name = _notetype_base_name(model["name"]) if model else None
        for section_name, section_ntss in sorted(section_to_ntss.items()):
            section = layout.collapsible_section(section_name)
            for nts in section_ntss:
                if general:
                    nts.add_widget_to_general_config_layout(section)
                else:
                    nts.add_widget_to_config_layout(
                        section, notetype_base_name=notetype_base_name, model=model
                    )
                section.space(7)
            layout.hseparator()
            layout.space(10)

        other_ntss: List[NotetypeSetting] = [
            nts for nts in ntss if nts not in nts_to_section.keys()
        ]
        for nts in other_ntss:
            if general:
                nts.add_widget_to_general_config_layout(layout)
            else:
                nts.add_widget_to_config_layout(
                    layout, notetype_base_name=notetype_base_name, model=model
                )
            layout.space(7)

    def _adjust_configurable_field_nts_order(
        self, ntss: List[NotetypeSetting], notetype_base_name: str
    ) -> List[NotetypeSetting]:
        # adjusts the order of the hint button settings to be the same as
        # on the original anking card
        # it would probably be better to check the order of the buttons on the current
        # version of the card, not the original one

        field_ntss = [
            nts for nts in ntss if nts.config.get("configurable_field_name", False)
        ]
        ordered_field_names = configurable_fields_for_notetype(notetype_base_name)
        ordered_field_ntss = sorted(
            field_ntss,
            key=lambda nts: (
                ordered_field_names.index(name)
                if (name := nts.config["configurable_field_name"])
                in ordered_field_names
                else -1  # can happen because of different quotes in template versions
            ),
        )

        other_ntss = [nts for nts in ntss if nts not in field_ntss]
        return other_ntss + ordered_field_ntss

    # tab actions
    def _set_active_tab(self, tab_name: str) -> None:
        tab_widget = self.window.main_tab
        tab_widget.setCurrentIndex(self._get_tab_idx_by_name(tab_name))

    def _reload_tab(self, tab_name: str) -> None:
        tab_widget = self.window.main_tab
        index = self._get_tab_idx_by_name(tab_name)
        tab_widget.removeTab(index)

        if tab_name == "Allgemein":
            self._add_general_tab(self.window)
        else:
            self._add_notetype_settings_tab(
                notetype_base_name=tab_name, window=self.window, index=index
            )

            self._read_in_settings()

        self.window.update_widgets()
        self._set_active_tab(tab_name)

    def _get_tab_idx_by_name(self, tab_name: str) -> int:
        tab_widget = self.window.main_tab
        return next(
            (
                index
                for index in range(tab_widget.count())
                if tab_name == tab_widget.tabText(index)
            ),
            None,
        )

    # reset / update / import notetypes
    # note: these actions can be called by clicking their buttons and will modify mw.col.models regardless
    # of whether the Save button is pressed after that
    def _reset_notetype_and_reload_ui(self, model: "NotetypeDict"):
        if not askUser(
            f"Willst du wirklich den Notiztyp <b>{model['name']}</b> auf Originaleinstellungen zurücksetzen?<br><br>"
            "Du musst danach eine Vollsynchronisierung mit AnkiWeb machen.<br>"
            "Stell sicher, dass du vorher alle anderen Geräte synchronisiert hast.",
            defaultno=True,
        ):
            return

        for model_version in _note_type_versions(model["name"]):
            update_notetype_to_newest_version(model_version, model["name"])
            mw.col.models.update_dict(model_version)  # type: ignore

        if self.clayout:
            self._update_clayout_model(model)

        self._reload_tab(_notetype_base_name(model["name"]))

        tooltip("Notiztyp wurde zurückgesetzt", parent=self.window, period=1200)

    def _reset_all_notetypes_and_reload_ui(self):
        if not askUser(
            "Willst du wirklich alle Notiztypen auf Originaleinstellungen zurücksetzen?<br><br>"
            "Du musst danach eine Vollsynchronisierung mit AnkiWeb machen.<br>"
            "Stell sicher, dass du vorher alle anderen Geräte synchronisiert hast.",
            defaultno=True,
        ):
            return

        for notetype_base_name in projekt_anki_notetype_names():
            for model_version in _note_type_versions(notetype_base_name):
                update_notetype_to_newest_version(model_version, notetype_base_name)
                mw.col.models.update_dict(model_version)  # type: ignore

        self._reload_tab("Allgemein")

        tooltip("Alle Notiztypen wurden zurückgesetzt", parent=self.window, period=1200)

    def _update_all_notetypes_to_newest_version_and_reload_ui(self):
        if not askUser(
            "Willst du die Notiztypen wirklich aktualisieren? Einstellungen bleiben erhalten.<br><br>"
            "Anschließend muss Anki vollständig mit AnkiWeb synchronisiert werden.<br>"
            "Stell sicher, dass du vorher alle anderen Geräte synchronisiert hast.",
            defaultno=True,
        ):
            return

        def task():
            to_be_updated = models_with_available_updates()
            for model in to_be_updated:
                # update the model to the newest version
                base_name = _notetype_base_name(model["name"])
                update_notetype_to_newest_version(model, base_name)

                # restore the values from before the update for the settings that exist in both versions
                self._safe_update_model_settings(
                    model=model,
                    notetype_base_name=base_name,
                    ntss=ntss_for_model(model),
                    show_tooltip_on_exception=False,
                )

                # update the model in the database
                mw.col.models.update_dict(model)

            return to_be_updated

        def on_done(updated_models_fut: Future):
            updated_models = updated_models_fut.result()

            for model in updated_models:
                if self.clayout and model["name"] == self.clayout.model["name"]:
                    self._update_clayout_model(model)

            self._reload_tab("Allgemein")
            updated_base_models = [
                m for m in updated_models if m["name"] == _notetype_base_name(m["name"])
            ]
            for model in sorted(updated_base_models, key=lambda m: m["name"]):
                self._reload_tab(_notetype_base_name(model["name"]))

            self._set_active_tab("Allgemein")

            tooltip("Notiztypen wurden aktualisiert", parent=self.window, period=1200)

        mw.taskman.with_progress(
            parent=self.window,
            label="Aktualisiere Notiztypen...",
            task=task,
            on_done=on_done,
            immediate=True,
        )

    def _import_notetype_and_reload_tab(self, notetype_base_name: str) -> None:
        self._import_notetype(notetype_base_name)
        self._reload_tab(notetype_base_name)

    def _import_notetype(self, notetype_base_name: str) -> None:
        model = projekt_anki_notetype_model(notetype_base_name)
        model["id"] = 0
        mw.col.models.add_dict(model)  # type: ignore

    # read / write notetype settings
    # changes to settings will be written to mw.col.models when the Save button is pressed
    # (on the add-ons' dialog or in Anki's note type manager window)
    # this is done by _apply_setting_changes_for_all_notetypes
    def _read_in_settings(self):
        # read in settings from notetypes and general ones into config
        self._read_in_settings_from_notetypes()
        self._read_in_general_settings()

    def _read_in_settings_from_notetypes(self):
        error_msg = ""
        for notetype_base_name in projekt_anki_notetype_names():
            if self.clayout and notetype_base_name == _notetype_base_name(
                self.clayout.model["name"]
            ):
                # if in live preview mode read in current not confirmed settings
                model = self.clayout.model
            else:
                model = _most_basic_notetype_version(notetype_base_name)

            if not model:
                continue
            for nts in ntss_for_model(model):
                try:
                    self.conf[nts.key(notetype_base_name)] = nts.setting_value(model)
                except NotetypeSettingException as e:
                    error_msg += f"failed parsing {notetype_base_name}:\n{str(e)}\n\n"

        if error_msg:
            showInfo(error_msg)

    def _read_in_general_settings(self):
        # read in default values
        for setting_name, value in general_settings_defaults_dict().items():
            self.conf.set(f"general.{setting_name}", value, on_change_trigger=False)

        # if all notetypes that have a nts have the same value set the value to it
        models_by_nts: Dict[NotetypeSetting, "NotetypeDict"] = defaultdict(lambda: [])
        for notetype_base_name in projekt_anki_notetype_names():
            model = _most_basic_notetype_version(notetype_base_name)
            if not model:
                continue

            ntss = ntss_for_model(model)
            for nts in ntss:
                models_by_nts[nts].append(model)

        for nts, models in models_by_nts.items():
            try:
                setting_value = nts.setting_value(models[0]) if models else None
                if all(setting_value == nts.setting_value(model) for model in models):
                    self.conf.set(
                        f"general.{nts.name()}", setting_value, on_change_trigger=False
                    )
            except NotetypeSettingException:
                pass

    def _safe_update_model_settings(
        self,
        model: "NotetypeDict",
        notetype_base_name: str,
        ntss: List["NotetypeSetting"],
        show_tooltip_on_exception=True,
    ) -> bool:
        """
        Updates the model with the passed settings. Returns True if successful, False if there was an exception.
        model: The model to update
        notetype_base_name: The base name of the note type. This is used to get the correct setting values from self.conf
        ntss: The settings to update
        """
        parse_exception = None
        for nts in ntss:
            try:
                model.update(
                    nts.updated_model(
                        model=model,
                        notetype_base_name=notetype_base_name,
                        conf=self.conf,
                    )
                )
            except NotetypeSettingException as e:
                parse_exception = e

        if parse_exception:
            message = f"failed parsing {model['name']}:\n{str(parse_exception)}"
            if show_tooltip_on_exception:
                tooltip(message)
            print(message)
            return False

        return True

    def _apply_setting_changes_for_all_notetypes(self):
        for notetype_base_name in projekt_anki_notetype_names():
            for model in _note_type_versions(notetype_base_name):
                if not model:
                    continue
                ntss = ntss_for_model(model)
                self._safe_update_model_settings(
                    model=model, notetype_base_name=notetype_base_name, ntss=ntss
                )
                mw.col.models.update_dict(model)

    # clayout
    def _update_clayout_model(self, model):
        # update templates
        # keep scrollbar in note type manager window where it was
        # add basic mark to the change tracker
        scroll_bar = self.clayout.tform.edit_area.verticalScrollBar()
        scroll_pos = scroll_bar.value()
        self.clayout.model = model
        self.clayout.templates = model["tmpls"]
        self.clayout.change_tracker.mark_basic()
        self.clayout.update_current_ordinal_and_redraw(self.clayout.ord)
        scroll_bar.setValue(min(scroll_pos, scroll_bar.maximum()))


def note_type_version(model: "NotetypeDict") -> Optional[str]:
    """Returns the version of the model or None if it is not specified.
    The version is specified on the top of the front template of the model."""
    front = model["tmpls"][0]["qfmt"]
    m = re.match(r"<!-- version ([\w\d]+) -->\n", front)
    if not m:
        return None
    return m.group(1)


def models_with_available_updates() -> List["NotetypeDict"]:
    return [
        model
        for notetype_base_name in projekt_anki_notetype_names()
        for model in _note_type_versions(notetype_base_name)
        if _new_version_available_for_model(model)
    ]


def _new_version_available_for_model(model: "NotetypeDict") -> bool:
    current_version = note_type_version(model)
    base_name = _notetype_base_name(model["name"])
    newest_version = note_type_version(projekt_anki_notetype_model(base_name))
    return current_version != newest_version


def _note_type_versions(notetype_base_name: str) -> List["NotetypeDict"]:
    """Returns a list of all notetype versions of the notetype in the collection.
    Version of a note type are created by the AnkiHub add-on and by copying
    the base AnKing note types or importing them from different sources."""
    models = [
        mw.col.models.get(x.id)  # type: ignore
        for x in mw.col.models.all_names_and_ids()
        if x.name == notetype_base_name
        or re.match(
            ANKIHUB_NOTETYPE_RE.format(notetype_base_name=notetype_base_name), x.name
        )
        or re.match(
            NOTETYPE_COPY_RE.format(notetype_base_name=notetype_base_name), x.name
        )
    ]
    return models


def _most_basic_notetype_version(notetype_base_name: str) -> Optional["NotetypeDict"]:
    """Returns the most basic version of a note type, that is the version with the shortest name."""
    model_versions = _note_type_versions(notetype_base_name)
    result = min(
        model_versions,
        # sort by length of name and then alphabetically
        key=lambda model: (len(model["name"]), model["name"]),
        default=None,
    )
    return result


def _notetype_base_name(model_name: str) -> str:
    """Returns the base name of a note type, that is if it's a version of a an anking note type
    it will return the base name, otherwise it will return the name itself."""
    return next(
        (
            notetype_base_name
            for notetype_base_name in projekt_anki_notetype_names()
            if re.match(rf"{notetype_base_name}($| |-)", model_name)
        ),
        None,
    )


def _names_of_all_supported_note_types() -> List[str]:
    """Returns a list of names of note types supported by the add-on that are in the collection,
    including all versions of the base note types."""
    return [
        version["name"]
        for notetype_base_name in projekt_anki_notetype_names()
        for version in _note_type_versions(notetype_base_name)
    ]
