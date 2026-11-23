"""Ankizin Startup Maintenance & Maintenance Center Dialog."""
from __future__ import annotations

from typing import Callable, Optional

from aqt import mw
from aqt.emptycards import EmptyCardsDialog
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import askUser, showInfo, tooltip

from ..compat import begin_undo_entry, finish_undo_entry, make_op_changes
from ..constants import ADDON_DIR_NAME
from ..ui import (
    COLORS,
    SegmentedControl,
    apply_ankizin_style,
    disable_auto_default,
    fit_dialog_to_screen,
    make_badge,
    make_card,
    make_header,
    make_wrapped_checkbox,
    resolve_parent,
)
from . import engine

_maintenance_dialog: Optional["MaintenanceDialog"] = None
_pending_reviewed_deletes: int = 0


def get_pending_reviewed_deletes() -> int:
    return _pending_reviewed_deletes


def _get_addon_conf() -> dict:
    if mw is None or getattr(mw, "addonManager", None) is None:
        return {}
    return mw.addonManager.getConfig(ADDON_DIR_NAME) or {}


def _write_addon_conf(conf: dict) -> None:
    if mw is not None and getattr(mw, "addonManager", None) is not None:
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)


def run_startup_maintenance(then: Callable[[], None]) -> None:
    """Quietly keep AnkiCollab auto-sync active and clean up unlearned !DELETE cards."""
    global _pending_reviewed_deletes
    if mw is None or not getattr(mw, "col", None):
        return then()

    conf = _get_addon_conf()
    if conf.get("auto_sync_ankicollab_on_startup", True):
        try:
            if engine.addon_status(engine.ANKICOLLAB_ADDON_ID) == "loaded":
                cur = engine.collab_get_settings()
                if not cur.get("pull_on_startup", False):
                    engine.collab_configure_settings(pull_on_startup=True, suspend_new_cards=None, preserve_deck_structure=None)
        except Exception as e:
            print(f"Ankizin: startup AnkiCollab settings check failed: {e}")

    mode = conf.get("auto_delete_marked_cards", "unlearned")
    if mode not in ("unlearned", "all", "manual"):
        mode = "unlearned"

    if mode == "manual":
        try:
            _, reviewed = engine.find_delete_marked_notes(mw.col)
            unlearned, _ = engine.find_delete_marked_notes(mw.col)
            _pending_reviewed_deletes = len(unlearned) + len(reviewed)
        except Exception:
            _pending_reviewed_deletes = 0
        return then()

    def op(col):
        unlearned, reviewed = engine.find_delete_marked_notes(col)
        if not unlearned and not reviewed:
            return engine.OpResult((0, 0), make_op_changes())
        target = begin_undo_entry(col, "!DELETE-Karten aufräumen")
        if mode == "all":
            deleted, skipped = engine.delete_marked_notes(col, include_reviewed=True)
        else:
            deleted, skipped = engine.delete_marked_notes(col, include_reviewed=False)
        changes = finish_undo_entry(col, target, card=True, note=True)
        return engine.OpResult((deleted, skipped), changes)

    def on_done(res: engine.OpResult) -> None:
        global _pending_reviewed_deletes
        deleted, skipped = res.value
        _pending_reviewed_deletes = skipped
        if deleted > 0:
            tooltip(
                f"Ankizin: {deleted} veraltete Karte{'n' if deleted != 1 else ''} (!DELETE) automatisch entfernt.",
                parent=mw,
                period=4500,
            )
        then()

    CollectionOp(mw, op).success(on_done).failure(lambda _e: then()).run_in_background()


class MaintenanceDialog(QDialog):
    """Unified 'Wartung & Einstellungen' center replacing fragmented Butler dialogs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(resolve_parent(parent, mw))
        self.setWindowTitle("Ankizin – Wartung & Einstellungen")
        apply_ankizin_style(self)
        fit_dialog_to_screen(self, 740, 620, 620, 480)
        self._build_ui()
        self._refresh_status()
        disable_auto_default(self, self._close_btn)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(
            make_header(
                "Wartung & Einstellungen",
                "Automatische Pflege für AnkiCollab, !DELETE-Karten, Datenbank und FSRS-Einstellungen",
            )
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("maint_scroll")
        scroll.setStyleSheet("#maint_scroll { border: none; background: transparent; }")
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(18, 16, 18, 16)
        body_lay.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── Card 1: AnkiCollab Sync & Settings ──────────────────────────────
        c_collab, l_collab = make_card()
        h1 = QHBoxLayout()
        t1 = QLabel("<b>AnkiCollab-Synchronisation</b>")
        self._collab_badge = make_badge("Prüfe…", "neutral")
        h1.addWidget(t1)
        h1.addStretch()
        h1.addWidget(self._collab_badge)
        l_collab.addLayout(h1)

        self._collab_desc = QLabel(
            "AnkiCollab hält dein Ankizin-Deck aktuell. Neue Karten aus Updates werden automatisch pausiert."
        )
        self._collab_desc.setWordWrap(True)
        l_collab.addWidget(self._collab_desc)

        pull_row, self._pull_startup_cb = make_wrapped_checkbox(
            "Beim Start von Anki automatisch nach Ankizin-Updates suchen",
            checked=True,
            bold_title=False,
        )
        susp_row, self._suspend_new_cb = make_wrapped_checkbox(
            "Neue Karten aus Updates automatisch pausieren (empfohlen)",
            checked=True,
            bold_title=False,
        )
        l_collab.addWidget(pull_row)
        l_collab.addWidget(susp_row)

        r1 = QHBoxLayout()
        self._update_now_btn = QPushButton("Jetzt nach Updates suchen")
        self._update_now_btn.clicked.connect(self._on_update_collab)
        self._wizard_btn = QPushButton("Einrichtungs-Assistent öffnen")
        self._wizard_btn.setObjectName("secondary")
        self._wizard_btn.clicked.connect(self._on_open_wizard)
        r1.addWidget(self._update_now_btn)
        r1.addWidget(self._wizard_btn)
        r1.addStretch()
        l_collab.addLayout(r1)
        body_lay.addWidget(c_collab)

        # ── Card 2: !DELETE & Housekeeping ──────────────────────────────────
        c_del, l_del = make_card()
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("<b>Veraltete Karten (!DELETE) & Aufräumen</b>"))
        h2.addStretch()
        self._del_badge = make_badge("0 gefunden", "success")
        h2.addWidget(self._del_badge)
        l_del.addLayout(h2)

        self._del_info = QLabel()
        self._del_info.setWordWrap(True)
        l_del.addWidget(self._del_info)

        auto_row = QHBoxLayout()
        auto_row.addWidget(QLabel("Beim Anki-Start:"))
        self._auto_del_combo = QComboBox()
        self._auto_del_combo.addItem("Nur ungelernte !DELETE-Karten automatisch löschen (Empfohlen)", "unlearned")
        self._auto_del_combo.addItem("Alle !DELETE-Karten automatisch löschen", "all")
        self._auto_del_combo.addItem("Nichts automatisch löschen (nur anzeigen)", "manual")
        auto_row.addWidget(self._auto_del_combo, 1)
        l_del.addLayout(auto_row)

        r2 = QHBoxLayout()
        self._del_unlearned_btn = QPushButton("Ungelernte !DELETE löschen")
        self._del_unlearned_btn.clicked.connect(lambda: self._on_delete_marked(False))
        self._del_all_btn = QPushButton("Alle !DELETE löschen")
        self._del_all_btn.setObjectName("danger_outline")
        self._del_all_btn.clicked.connect(lambda: self._on_delete_marked(True))
        self._db_check_btn = QPushButton("Leere Karten & Datenbank prüfen")
        self._db_check_btn.setObjectName("secondary")
        self._db_check_btn.clicked.connect(self._on_housekeeping)
        r2.addWidget(self._del_unlearned_btn)
        r2.addWidget(self._del_all_btn)
        r2.addWidget(self._db_check_btn)
        r2.addStretch()
        l_del.addLayout(r2)
        body_lay.addWidget(c_del)

        # ── Card 3: Optimal FSRS & High-Yield Settings ──────────────────────
        c_fsrs, l_fsrs = make_card()
        l_fsrs.addWidget(QLabel("<b>Empfohlene Ankizin-Lerneinstellungen (FSRS)</b>"))
        fsrs_desc = QLabel(
            "Aktiviert FSRS, setzt sinnvolle Lernschritte (15 min), Max-Intervall 3600 Tage (ohne künstliche Begrenzung), "
            "zeigt Wiederholungen vor neuen Karten und schützt nur den Ankizin-Stapel mit einem eigenen Preset."
        )
        fsrs_desc.setWordWrap(True)
        l_fsrs.addWidget(fsrs_desc)

        pace_row = QHBoxLayout()
        pace_row.addWidget(QLabel("Tägliches Limit neuer Karten:"))
        self._pace_seg = SegmentedControl(
            [
                ("20", "Entspannt (20)", "Ca. 160–240 Wiederholungen/Tag"),
                ("40", "Empfohlen (40)", "Ca. 320–400 Wiederholungen/Tag"),
                ("60", "Intensiv (60)", "Ca. 480–600 Wiederholungen/Tag"),
            ],
            initial_key="40",
        )
        pace_row.addWidget(self._pace_seg)
        pace_row.addStretch()
        l_fsrs.addLayout(pace_row)

        r3 = QHBoxLayout()
        self._apply_fsrs_btn = QPushButton("Empfohlene Einstellungen anwenden")
        self._apply_fsrs_btn.clicked.connect(self._on_apply_fsrs)
        self._flag_hy_btn = QPushButton("High-Yield farblich flaggen")
        self._flag_hy_btn.setObjectName("secondary")
        self._flag_hy_btn.setToolTip("Markiert stark gelbe Karten rot und leicht gelbe orange (nur ohne eigene Flagge).")
        self._flag_hy_btn.clicked.connect(self._on_flag_high_yield)
        r3.addWidget(self._apply_fsrs_btn)
        r3.addWidget(self._flag_hy_btn)
        r3.addStretch()
        l_fsrs.addLayout(r3)
        body_lay.addWidget(c_fsrs)

        # ── Card 4: UI & Smart Decks Preferences ────────────────────────────
        c_ui, l_ui = make_card()
        l_ui.addWidget(QLabel("<b>Startseite & Auswahlstapel</b>"))
        qb_row, self._quickbar_cb = make_wrapped_checkbox(
            "Ankizin-Schnellstartleiste auf der Anki-Startseite anzeigen",
            checked=True,
            bold_title=False,
        )
        reb_row, self._rebuild_cb = make_wrapped_checkbox(
            "Auswahlstapel & Smart-Stapel beim Anki-Start automatisch aktualisieren",
            checked=True,
            bold_title=False,
        )
        only_row, self._only_ankizin_cb = make_wrapped_checkbox(
            "…nur Ankizin-Stapel (eigene Auswahlstapel unverändert lassen)",
            checked=False,
            bold_title=False,
        )
        l_ui.addWidget(qb_row)
        l_ui.addWidget(reb_row)
        l_ui.addWidget(only_row)
        body_lay.addWidget(c_ui)
        body_lay.addStretch()

        # ── Footer ──────────────────────────────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {COLORS['border']}; border: none;")
        root.addWidget(line)

        footer = QHBoxLayout()
        footer.setContentsMargins(18, 12, 18, 12)
        footer.addStretch()
        self._save_btn = QPushButton("Einstellungen speichern")
        self._save_btn.setObjectName("secondary")
        self._save_btn.clicked.connect(self._on_save_prefs)
        self._close_btn = QPushButton("Fertig")
        self._close_btn.clicked.connect(self._on_save_and_close)
        footer.addWidget(self._save_btn)
        footer.addWidget(self._close_btn)
        root.addLayout(footer)

    def _refresh_status(self) -> None:
        conf = _get_addon_conf()
        info = engine.detect_setup_state()

        if info["collab_status"] != "loaded":
            self._collab_badge.setText("Nicht installiert")
            self._pull_startup_cb.setEnabled(False)
            self._suspend_new_cb.setEnabled(False)
            self._update_now_btn.setEnabled(False)
        elif not info["collab_logged_in"]:
            self._collab_badge.setText("Anmeldung nötig")
            self._update_now_btn.setEnabled(False)
        else:
            self._collab_badge.setText("Aktiv ✓")
            self._update_now_btn.setEnabled(True)

        cs = info.get("collab_settings") or {}
        self._pull_startup_cb.setChecked(bool(cs.get("pull_on_startup", conf.get("auto_sync_ankicollab_on_startup", True))))
        self._suspend_new_cb.setChecked(bool(cs.get("suspend_new_cards", True)))

        unlearned, reviewed = engine.find_delete_marked_notes(mw.col if mw else None)
        total_del = len(unlearned) + len(reviewed)
        self._del_badge.setText(f"{total_del} gefunden" if total_del else "Alles sauber ✓")
        self._del_info.setText(
            f"<b>{len(unlearned)}</b> ungelernte und <b>{len(reviewed)}</b> bereits gelernte Karten mit <code>!DELETE</code> gefunden. "
            "Bei bereits gelernten Karten kannst du selbst entscheiden, ob du deinen Lernfortschritt behalten willst."
        )
        self._del_unlearned_btn.setEnabled(len(unlearned) > 0)
        self._del_all_btn.setEnabled(total_del > 0)

        mode = conf.get("auto_delete_marked_cards", "unlearned")
        idx = self._auto_del_combo.findData(mode)
        self._auto_del_combo.setCurrentIndex(max(0, idx))

        self._quickbar_cb.setChecked(bool(conf.get("show_home_quickbar", True)))
        self._rebuild_cb.setChecked(bool(conf.get("autoRebuildDecksOnStartup", True)))
        self._only_ankizin_cb.setChecked(bool(conf.get("autoRebuildOnlyAnkizinDecks", False)))

    def _on_save_prefs(self, show_toast: bool = True) -> None:
        conf = _get_addon_conf()
        conf["auto_delete_marked_cards"] = self._auto_del_combo.currentData()
        conf["auto_sync_ankicollab_on_startup"] = self._pull_startup_cb.isChecked()
        conf["show_home_quickbar"] = self._quickbar_cb.isChecked()
        conf["autoRebuildDecksOnStartup"] = self._rebuild_cb.isChecked()
        conf["autoRebuildOnlyAnkizinDecks"] = self._only_ankizin_cb.isChecked()
        _write_addon_conf(conf)

        if engine.addon_status(engine.ANKICOLLAB_ADDON_ID) == "loaded":
            engine.collab_configure_settings(
                pull_on_startup=self._pull_startup_cb.isChecked(),
                suspend_new_cards=self._suspend_new_cb.isChecked(),
            )
        if show_toast:
            tooltip("Einstellungen gespeichert.", parent=self, period=2500)
        if mw and mw.state == "deckBrowser":
            mw.deckBrowser.refresh()

    def _on_save_and_close(self) -> None:
        self._on_save_prefs(show_toast=False)
        self.accept()

    def _on_update_collab(self) -> None:
        if engine.collab_trigger_update():
            tooltip("AnkiCollab prüft auf Updates…", parent=self, period=3000)
        else:
            showInfo("Bitte prüfe über AnkiCollab → Update Decks im Menü.", parent=self)

    def _on_open_wizard(self) -> None:
        from .wizard import open_setup_wizard
        self.close()
        open_setup_wizard(force=True)

    def _on_delete_marked(self, include_reviewed: bool) -> None:
        if include_reviewed and not askUser(
            "Möchtest du wirklich ALLE !DELETE-Karten löschen — auch solche, die du bereits gelernt hast?",
            parent=self,
            defaultno=True,
        ):
            return

        def op(col):
            target = begin_undo_entry(col, "!DELETE-Karten löschen")
            deleted, skipped = engine.delete_marked_notes(col, include_reviewed=include_reviewed)
            return engine.OpResult((deleted, skipped), finish_undo_entry(col, target, card=True, note=True))

        def done(res: engine.OpResult) -> None:
            global _pending_reviewed_deletes
            deleted, skipped = res.value
            _pending_reviewed_deletes = skipped
            tooltip(f"{deleted} !DELETE-Notizen gelöscht.", parent=self, period=3000)
            self._refresh_status()
            if mw:
                mw.reset()

        CollectionOp(self, op).success(done).run_in_background()

    def _on_housekeeping(self) -> None:
        def op(col):
            col.tags.clear_unused_tags()
            return col.get_empty_cards()

        def after_empty(report) -> None:
            if report.notes:
                EmptyCardsDialog(mw, report).show()

            def on_integrity(result: tuple[str, bool]) -> None:
                msg, ok = result
                showInfo(
                    "Datenbank ist in Ordnung!" if ok else f"Datenbank-Prüfung:\n{msg}",
                    parent=self,
                )
                mw.reset()

            QueryOp(self, lambda col: col.fix_integrity(), success=on_integrity).with_progress(
                "Datenbank wird geprüft..."
            ).run_in_background()

        QueryOp(self, op, success=after_empty).with_progress("Suche leere Karten...").run_in_background()

    def _on_apply_fsrs(self) -> None:
        per_day = int(self._pace_seg.current_key() or "40")

        def op(col):
            res = engine.apply_recommended_ankizin_settings(col, new_per_day=per_day, max_ivl=3600)
            return engine.OpResult(res, make_op_changes(config=True, deck_config=True))

        def done(out: engine.OpResult) -> None:
            res = out.value
            engine.update_setup_state(configured=True)
            showInfo(
                f"FSRS und optimale Ankizin-Einstellungen ({res['new_per_day']} neue Karten/Tag) "
                f"auf {res['decks_assigned']} Stapel angewendet!",
                parent=self,
            )

        CollectionOp(self, op).success(done).run_in_background()

    def _on_flag_high_yield(self) -> None:
        def op(col):
            target = begin_undo_entry(col, "Ankizin High-Yield markieren")
            stark, leicht = engine.flag_high_yield_cards(col)
            return engine.OpResult((stark, leicht), finish_undo_entry(col, target, card=True))

        def done(out: engine.OpResult) -> None:
            stark, leicht = out.value
            showInfo(
                f"{stark} stark-gelbe (rot) und {leicht} leicht-gelbe (orange) Karten markiert.",
                parent=self,
            )

        CollectionOp(self, op).success(done).run_in_background()


def open_maintenance_dialog(parent: Optional[QWidget] = None) -> None:
    global _maintenance_dialog
    if _maintenance_dialog is not None:
        try:
            if _maintenance_dialog.isVisible():
                _maintenance_dialog.raise_()
                _maintenance_dialog.activateWindow()
                return
        except RuntimeError:
            pass
    _maintenance_dialog = MaintenanceDialog(parent or mw)
    _maintenance_dialog.show()
