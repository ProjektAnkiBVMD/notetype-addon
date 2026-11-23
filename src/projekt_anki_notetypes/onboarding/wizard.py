"""Guided Ankizin Onboarding & AnkiCollab Migration Wizard.

Guides complete Anki beginners ("DAU-sicher") as well as AnkiHub/.apkg
migrators step-by-step through installing AnkiCollab, creating/signing in
to a free account, migrating safely with backups, downloading Ankizin,
applying recommended FSRS settings, and jumping straight into the Lern-Zentrale.
"""
from __future__ import annotations

import html
import time
import webbrowser
from typing import Callable, Optional

from aqt import mw
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QObject,
    QPushButton,
    QScrollArea,
    QThread,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    pyqtSignal,
)
from aqt.utils import tooltip

from ..compat import create_backup_now
from ..constants import ADDON_DIR_NAME
from ..ui import (
    COLORS,
    SegmentedControl,
    StepRail,
    apply_ankizin_style,
    disable_auto_default,
    fit_dialog_to_screen,
    make_card,
    make_header,
    make_wrapped_checkbox,
    resolve_parent,
)
from . import engine

ANKICOLLAB_ANKIWEB_PAGE = "https://ankiweb.net/shared/info/1957538407"
DAY_SECS = 24 * 60 * 60
_PAIR_TTL_SECONDS = 300
_PAIR_POLL_INTERVAL_MS = 2000

_ACTIVE_PAIR_WORKERS: set[QThread] = set()


class _PairInitWorker(QThread):
    result = pyqtSignal(object)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        _ACTIVE_PAIR_WORKERS.add(self)
        self.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        _ACTIVE_PAIR_WORKERS.discard(self)
        self.deleteLater()

    def run(self) -> None:
        self.result.emit(engine.collab_pair_init())


class _PairPollWorker(QThread):
    result = pyqtSignal(object)

    def __init__(self, poll_token: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._poll_token = poll_token
        _ACTIVE_PAIR_WORKERS.add(self)
        self.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        _ACTIVE_PAIR_WORKERS.discard(self)
        self.deleteLater()

    def run(self) -> None:
        self.result.emit(engine.collab_pair_poll(self._poll_token))

STEPS = {
    "welcome": "Willkommen",
    "install": "AnkiCollab installieren",
    "account": "AnkiCollab-Konto",
    "prepare": "Sicherung & Vorbereitung",
    "ankihub": "AnkiHub trennen",
    "aside": "Alten Stapel sichern",
    "download": "Ankizin herunterladen",
    "configure": "Optimal einrichten",
    "save": "Mit AnkiWeb sichern",
    "finish": "Fertig & loslernen",
}

BLURBS = {
    "install": "Kostenloses Add-on <b>AnkiCollab</b> installieren und Anki einmal kurz neu starten",
    "account": "Kostenloses <b>AnkiCollab-Konto</b> anlegen &amp; mit einem Klick anmelden",
    "prepare": "Aktuelle Sammlung mit AnkiWeb synchronisieren und eine Sicherheitskopie anlegen",
    "ankihub": "AnkiHub für Ankizin sauber trennen (andere AnkiHub-Decks bleiben unberührt)",
    "aside": "Dein bisheriges Ankizin-Deck sicher als <code>Ankizin_alt</code> beiseite legen",
    "download": "Aktuelles <b>Ankizin-Deck</b> laden (bisheriger Lernfortschritt bleibt erhalten)",
    "configure": "Neue Karten pausieren, FSRS-Lerneinstellungen optimieren &amp; <code>!DELETE</code> bereinigen",
    "save": "Änderungen mit AnkiWeb synchronisieren (für iPad, Handy &amp; Backup)",
}

_wizard: Optional["AnkizinSetupWizard"] = None


def build_plan(info: dict) -> list[str]:
    """Compute minimal ordered list of wizard steps for the user's current state."""
    scenario = info["scenario"]
    signed_in = bool(info.get("collab_logged_in"))
    collab_loaded = info.get("collab_status") == "loaded"
    subscribed = bool(info.get("subscribed"))
    installed_did = int(info.get("installed_did") or 0)
    configured = bool(info.get("configured"))

    if scenario == "ready":
        return ["finish"]

    plan = ["welcome"]
    if scenario == "dual":
        if info.get("old_decks") or info.get("ankihub_decks"):
            plan.append("prepare")
        plan.append("ankihub")
        if not collab_loaded:
            plan.append("install")
        if not signed_in:
            plan.append("account")
        if not installed_did:
            plan.append("download")
        if not configured:
            plan.append("configure")
    elif scenario == "incomplete":
        if not collab_loaded:
            plan.append("install")
        if not signed_in:
            plan.append("account")
        if not subscribed or not installed_did:
            plan.append("download")
        if not configured:
            plan.append("configure")
    else:
        # new | migrate_ankihub | migrate_apkg
        if not collab_loaded:
            plan.append("install")
        if not signed_in:
            plan.append("account")
        if info.get("ankihub_decks") or info.get("old_decks") or info.get("has_content"):
            plan.append("prepare")
        if info.get("ankihub_decks"):
            plan.append("ankihub")
        if info.get("old_decks"):
            plan.append("aside")
        plan.append("download")
        plan.append("configure")

    if info.get("ankiweb") and any(s in plan for s in ("ankihub", "aside", "download", "configure")):
        plan.append("save")
    plan.append("finish")
    return plan


def _bullets(lines: list[str]) -> str:
    items = "".join(f"<li style='margin-bottom:5px;'>{line}</li>" for line in lines)
    return f"<ul style='margin-left:-18px;'>{items}</ul>"


class AnkizinSetupWizard(QDialog):
    """Step-by-step guided setup wizard for new users and migrators."""

    _REVISITABLE = ("welcome", "account")
    _POINT_OF_NO_RETURN = ("prepare", "ankihub", "aside", "download", "configure")

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        resumed: bool = False,
        info_override: Optional[dict] = None,
    ) -> None:
        super().__init__(resolve_parent(parent, mw))
        self.setWindowTitle("Ankizin Einrichtungs-Assistent")
        apply_ankizin_style(self)
        fit_dialog_to_screen(self, 920, 660, 740, 520)

        self.resumed = resumed
        self.info = info_override if info_override is not None else engine.detect_setup_state()
        self.settings = self.info["settings"]
        self.key = self.info["deck_key"]
        self.plan = build_plan(self.info)
        self.current: Optional[str] = None
        self.done_steps: set[str] = set()
        self.skipped: set[str] = set()
        self.summary: list[str] = []
        self.safe_to_upload = False
        self.save_skipped = False
        self.ankihub_still_on_server: list[str] = []
        self.aside_dids: list[int] = []
        self.aside_lines: dict[int, str] = {}
        self.changed_notetypes = False
        self.busy = False

        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_download)
        self._pull_finished_at: Optional[float] = None

        self._pair_code = ""
        self._pair_token = ""
        self._pair_outstanding = ""
        self._pair_then: Optional[Callable] = None
        self._pair_closing = False
        self._pair_attempt_id = 0
        self._pair_poll_timer = QTimer(self)
        self._pair_poll_timer.setInterval(_PAIR_POLL_INTERVAL_MS)
        self._pair_poll_timer.timeout.connect(self._pair_poll_once)
        self._pair_expiry_timer = QTimer(self)
        self._pair_expiry_timer.setSingleShot(True)
        self._pair_expiry_timer.timeout.connect(self._on_pair_expired)

        self._build_ui()
        self.finished.connect(self._on_closed)
        self.go(self.plan[0])

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(
            make_header(
                "Ankizin Einrichtungs-Assistent",
                "Schritt für Schritt zum fertigen Ankizin-Deck — ganz ohne Vorwissen",
            )
        )

        body = QHBoxLayout()
        body.setContentsMargins(14, 10, 14, 10)
        body.setSpacing(12)
        outer.addLayout(body, 1)

        rail_steps = [(s, self._step_name(s)) for s in self.plan]
        self._rail = StepRail(rail_steps)
        self._rail.step_clicked.connect(self._go_back)
        body.addWidget(self._rail)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background: {COLORS['border']}; border: none;")
        body.addWidget(sep)

        page_col = QVBoxLayout()
        page_col.setSpacing(10)

        self._title_lbl = QLabel()
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setStyleSheet(
            f"font-size: 19px; font-weight: 700; color: {COLORS['accent']}; background: transparent;"
        )
        page_col.addWidget(self._title_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("wizard_scroll")
        scroll.setStyleSheet("#wizard_scroll { border: none; background: transparent; }")

        content = QWidget()
        content.setObjectName("wizard_content")
        content.setStyleSheet("#wizard_content { background: transparent; }")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 6, 0)
        content_lay.setSpacing(8)
        scroll.setWidget(content)
        page_col.addWidget(scroll, 1)

        self._body_lbl = QLabel()
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._body_lbl.setOpenExternalLinks(True)
        self._body_lbl.setStyleSheet("font-size: 13px; line-height: 145%; background: transparent;")
        self._body_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        content_lay.addWidget(self._body_lbl)

        self._extra_lay = QVBoxLayout()
        self._extra_lay.setSpacing(8)
        content_lay.addLayout(self._extra_lay)

        self._status_lbl = QLabel()
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._status_lbl.setOpenExternalLinks(True)
        content_lay.addWidget(self._status_lbl)
        content_lay.addStretch()

        self._buttons_lay = QHBoxLayout()
        self._buttons_lay.setSpacing(10)
        page_col.addLayout(self._buttons_lay)
        body.addLayout(page_col, 1)

    def _step_name(self, step: str) -> str:
        if step == "prepare" and not self.info.get("ankiweb"):
            return "Sicherung anlegen"
        return STEPS[step]

    def _can_go_back(self, step: str) -> bool:
        return (
            step in self._REVISITABLE
            and step != self.current
            and not self.busy
            and (step in self.done_steps or step in self.skipped)
            and not any(s in self.done_steps or s == self.current for s in self._POINT_OF_NO_RETURN)
        )

    def _go_back(self, step: str) -> None:
        if self._can_go_back(step):
            self.skipped.discard(step)
            self.done_steps.discard(step)
            self.go(step)

    def _refresh_rail(self) -> None:
        self._rail.set_state(self.current or "", self.done_steps, self.skipped, self._can_go_back)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _page(
        self,
        title: str,
        body_html: str,
        primary: Optional[tuple[str, Callable]] = None,
        secondary: Optional[tuple[str, Callable]] = None,
        link: Optional[tuple[str, Callable]] = None,
    ) -> None:
        self._title_lbl.setText(title)
        self._body_lbl.setText(body_html)
        self._status_lbl.setText("")
        self._clear_layout(self._extra_lay)
        self._set_buttons(primary, secondary, link)

    def _set_buttons(
        self,
        primary: Optional[tuple[str, Callable]] = None,
        secondary: Optional[tuple[str, Callable]] = None,
        link: Optional[tuple[str, Callable]] = None,
    ) -> None:
        self._clear_layout(self._buttons_lay)
        if link:
            text, cb = link
            lbl = QLabel(f"<a href='#' style='color:gray;text-decoration:none;'>{text}</a>")
            lbl.linkActivated.connect(lambda _=None, fn=cb: fn())
            self._buttons_lay.addWidget(lbl)
        self._buttons_lay.addStretch()
        primary_btn = None
        if secondary:
            btn = QPushButton(secondary[0])
            btn.setObjectName("secondary")
            btn.clicked.connect(lambda _=False, fn=secondary[1]: fn())
            self._buttons_lay.addWidget(btn)
        if primary:
            primary_btn = QPushButton(primary[0])
            primary_btn.clicked.connect(lambda _=False, fn=primary[1]: fn())
            self._buttons_lay.addWidget(primary_btn)
        disable_auto_default(self, primary_btn)

    def _working(self, text: str) -> None:
        self.busy = True
        self._status_lbl.setText(f"<span style='color:{COLORS['accent']};font-weight:600;'>⏳ {text}</span>")
        self._set_buttons()
        QApplication.processEvents()

    def _error(self, text: str, retry: Optional[Callable] = None, link: Optional[tuple[str, Callable]] = None) -> None:
        self.busy = False
        self._status_lbl.setText(f"<span style='color:{COLORS['danger']};'>{text}</span>")
        self._set_buttons(
            primary=("Erneut versuchen", retry) if retry else None,
            secondary=("Schließen", self.close),
            link=link,
        )

    def go(self, step: str) -> None:
        self._stop_pairing()
        self.current = step
        self.busy = False
        self._refresh_rail()
        getattr(self, f"_page_{step}")()

    def next(self) -> None:
        if self.current:
            self.skipped.discard(self.current)
            self.done_steps.add(self.current)
            idx = self.plan.index(self.current)
            if idx + 1 < len(self.plan):
                self.go(self.plan[idx + 1])

    def skip(self) -> None:
        if self.current:
            self.skipped.add(self.current)
            idx = self.plan.index(self.current)
            if idx + 1 < len(self.plan):
                self.go(self.plan[idx + 1])

    # ── Wizard Pages ─────────────────────────────────────────────────────────

    def _page_welcome(self) -> None:
        scenario = self.info["scenario"]
        blurbs = dict(BLURBS)
        if self.info.get("collab_status") == "disabled":
            blurbs["install"] = "Das vorhandene Add-on <b>AnkiCollab</b> wieder einschalten und Anki kurz neu starten"
        if not self.info.get("ankiweb"):
            blurbs["prepare"] = "Eine vollständige Sicherheitskopie deiner Sammlung anlegen"
        if scenario == "new":
            blurbs["download"] = "Das aktuelle <b>Ankizin-Deck</b> direkt über AnkiCollab herunterladen"

        upcoming = [blurbs[s] for s in self.plan if s in blurbs]
        intro = "<p><b>Willkommen zurück! Lass uns genau dort weitermachen, wo wir aufgehört haben.</b></p>" if self.resumed else ""

        if scenario == "dual":
            title = "AnkiHub & AnkiCollab entwirren"
            body = (
                intro
                + "<p>Ankizin wird aktuell sowohl über <b>AnkiHub</b> als auch über <b>AnkiCollab</b> aktualisiert. "
                "Beide gleichzeitig können Änderungen überschreiben.</p>"
                "<p><b>Keine Sorge: Dein Lernfortschritt bleibt komplett erhalten.</b></p>"
                "<p>Das macht der Assistent jetzt automatisch:</p>"
                + _bullets(upcoming)
            )
        elif scenario == "migrate_ankihub":
            title = "Umzug von AnkiHub zu AnkiCollab"
            body = (
                intro
                + "<p>Wir haben eine ältere AnkiHub-Version (<code>#Ankizin_vAnkihub</code>) erkannt. "
                "Ankizin nutzt jetzt ausschließlich das kostenlose <b>AnkiCollab</b> (<code>#Ankizin_vAnkiCollab</code>).</p>"
                "<p><b>Dein gesamter Lernfortschritt und deine Wiederholungen bleiben 100% erhalten!</b></p>"
                "<p>Das passiert in den nächsten Schritten automatisch:</p>"
                + _bullets(upcoming)
            )
        elif scenario == "migrate_apkg":
            legacy_list = (self.info.get("tag_sources") or {}).get("legacy_versions") or []
            ver_txt = f" ({', '.join(legacy_list)})" if legacy_list else ""
            title = "Auf AnkiCollab aktualisieren"
            body = (
                intro
                + f"<p>Du nutzt bereits eine ältere Datei-Version von Ankizin{ver_txt}. Mit dem kostenlosen "
                "<b>AnkiCollab</b> erhältst du automatisch neue Karten und Korrekturen, ohne jemals wieder manuell "
                "Dateien importieren zu müssen.</p>"
                "<p><b>Dein Lernfortschritt bleibt vollständig erhalten.</b></p>"
                + _bullets(upcoming)
            )
        elif scenario == "incomplete":
            title = "Ankizin-Einrichtung abschließen"
            body = (
                intro
                + "<p>Ein paar Schritte fehlen noch, bis dein Ankizin perfekt eingerichtet ist:</p>"
                + _bullets(upcoming)
            )
        else:
            title = "Willkommen bei Ankizin!"
            body = (
                intro
                + "<p>Schön, dass du da bist! Du musst Anki vorher noch nie benutzt haben — "
                "dieser Assistent übernimmt die komplette Einrichtung für dich.</p>"
                "<p>In wenigen Minuten erledigen wir gemeinsam:</p>"
                + _bullets(upcoming)
                + "<p style='color:gray;'>Tipp: Bleibe während des Downloads mit stabilem WLAN verbunden.</p>"
            )

        self._page(
            title,
            body,
            primary=("Weiter" if self.resumed else "Los geht's!", self.next),
            secondary=("Später", self.close),
        )

    # Install AnkiCollab -----------------------------------------------------

    def _page_install(self) -> None:
        status = engine.addon_status(engine.ANKICOLLAB_ADDON_ID)
        if status == "loaded":
            self.next()
            return
        if status == "restart":
            self._page(
                "Anki einmal kurz neu starten",
                "<p><b>AnkiCollab ist jetzt installiert!</b> Anki muss einmal neu gestartet werden, damit es aktiv wird.</p>"
                "<p>Klicke unten auf <b>Anki jetzt schließen</b> und öffne Anki danach einfach wieder. "
                "<b>Dieser Assistent öffnet sich nach dem Neustart automatisch wieder hier!</b></p>",
                primary=("Anki jetzt schließen", self._restart_anki),
                secondary=("Ich starte später neu", self._restart_later),
            )
            return
        if status == "disabled":
            self._page(
                "AnkiCollab aktivieren",
                "<p>AnkiCollab ist bereits installiert, aber aktuell deaktiviert. Wir schalten es jetzt für dich ein.</p>",
                primary=("AnkiCollab einschalten", self._install),
                secondary=("Abbrechen", self.close),
            )
            return

        self._page(
            "AnkiCollab automatisch installieren",
            "<p><b>AnkiCollab</b> ist die kostenlose Erweiterung, über die das Ankizin-Deck heruntergeladen "
            "und laufend aktuell gehalten wird.</p>"
            "<p>Mit einem Klick laden wir AnkiCollab direkt von AnkiWeb für dich herunter.</p>",
            primary=("AnkiCollab installieren", self._install),
            secondary=("Abbrechen", self.close),
        )

    def _install(self) -> None:
        switching_on = engine.addon_status(engine.ANKICOLLAB_ADDON_ID) == "disabled"
        self._working("Aktiviere AnkiCollab…" if switching_on else "Lade AnkiCollab von AnkiWeb herunter…")

        def done(ok: bool, _msg: str) -> None:
            if ok:
                self.summary.append("AnkiCollab aktiviert" if switching_on else "AnkiCollab installiert")
                self._page_install()
            else:
                self._error(
                    "AnkiCollab konnte nicht heruntergeladen werden. Bitte prüfe deine Internetverbindung.",
                    retry=self._install,
                    link=("Auf AnkiWeb manuell öffnen", lambda: webbrowser.open(ANKICOLLAB_ANKIWEB_PAGE)),
                )

        engine.install_ankicollab(done)

    def _restart_later(self) -> None:
        engine.update_setup_state(resume=True)
        tooltip("Die Einrichtung macht beim nächsten Anki-Start automatisch weiter.", parent=mw, period=5000)
        self.close()

    def _restart_anki(self) -> None:
        engine.update_setup_state(resume=True)
        self.close()
        if mw:
            mw.close()

    # AnkiCollab Account -----------------------------------------------------

    def _page_account(self) -> None:
        if engine.collab_is_logged_in():
            self.next()
            return

        self._page(
            "Dein kostenloses AnkiCollab-Konto",
            "<p>Um das Ankizin-Deck herunterzuladen, brauchst du ein kostenloses <b>AnkiCollab-Konto</b> "
            "(eigenes Konto, unabhängig von AnkiWeb). Anmeldung und Kontoerstellung öffnen deinen gewohnten "
            "<b>Standard-Browser</b> — so funktionieren <b>Passkeys</b>, iCloud-Schlüsselbund / Windows Hello "
            "und Passwortmanager (z. B. Bitwarden) zuverlässig.</p>",
            primary=("Jetzt mit Anki verbinden", self._sign_in),
            secondary=("Später", self.close),
        )

        card1, lay1 = make_card("ankizin_card_soft")
        lay1.addWidget(QLabel("<b>Schritt 1: Noch kein Konto?</b>"))
        l1 = QLabel(
            "Erstelle in 30 Sekunden dein kostenloses Konto auf ankicollab.com. "
            "Dein Browser kann Passwort oder Passkey dabei direkt sicher speichern."
        )
        l1.setWordWrap(True)
        lay1.addWidget(l1)
        signup_btn = QPushButton("Kostenloses Konto im Browser erstellen ↗")
        signup_btn.setObjectName("secondary")
        signup_btn.setAutoDefault(False)
        signup_btn.clicked.connect(self._sign_up)
        lay1.addWidget(signup_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self._extra_lay.addWidget(card1)

        card2, lay2 = make_card("ankizin_card_accent")
        lay2.addWidget(QLabel("<b>Schritt 2: Mit Anki verbinden</b>"))
        l2 = QLabel(
            "Klicke unten auf <b>Jetzt mit Anki verbinden</b>. Dein Browser öffnet eine kurze "
            "Bestätigungsseite — sobald du dort bestätigst, geht es hier <b>automatisch</b> weiter."
        )
        l2.setWordWrap(True)
        lay2.addWidget(l2)
        classic_btn = QPushButton("Lieber mit Passwort anmelden (klassisches Fenster)")
        classic_btn.setObjectName("ghost")
        classic_btn.setAutoDefault(False)
        classic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        classic_btn.clicked.connect(self._sign_in_classic)
        lay2.addWidget(classic_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self._extra_lay.addWidget(card2)

    def _record_logged_in(self) -> None:
        if "Bei AnkiCollab angemeldet" not in self.summary:
            self.summary.append("Bei AnkiCollab angemeldet")

    def _sign_up(self) -> None:
        webbrowser.open(engine.collab_signup_url())
        self._status_lbl.setText(
            f"<span style='color:{COLORS['accent']};'>Konto im Browser erstellt? "
            "Dann klicke unten rechts auf <b>Jetzt mit Anki verbinden</b>.</span>"
        )

    def _sign_in(self, then: Optional[Callable] = None) -> None:
        if engine.collab_is_logged_in():
            self._stop_pairing()
            self._record_logged_in()
            (then or self.next)()
            return
        self._start_pairing(then=then)

    def _start_pairing(self, then: Optional[Callable] = None) -> None:
        self._stop_pairing()
        self._pair_attempt_id += 1
        attempt_id = self._pair_attempt_id
        self._pair_then = then
        self._status_lbl.setText(
            f"<span style='color:{COLORS['accent']};font-weight:600;'>"
            "⏳ Verbindungscode wird bei AnkiCollab angefordert…</span>"
        )
        parent = mw if isinstance(mw, QObject) else None
        worker = _PairInitWorker(parent=parent)
        worker.result.connect(lambda payload, aid=attempt_id: self._on_pair_init_result(payload, aid))
        worker.start()

    def _on_pair_init_result(self, payload: dict, attempt_id: Optional[int] = None) -> None:
        if self._pair_closing:
            return
        if attempt_id is not None and attempt_id != self._pair_attempt_id:
            return
        if not isinstance(payload, dict) or not payload.get("ok"):
            err = html.escape(str((payload or {}).get("error") or "Verbindungscode konnte nicht angefordert werden."))
            self._status_lbl.setText(
                f"<span style='color:{COLORS['danger']};'>{err} "
                "Klicke einfach erneut auf <b>Jetzt mit Anki verbinden</b> oder nutze unten das klassische Passwort-Fenster.</span>"
            )
            return

        code = str(payload.get("code", "")).strip()
        token = str(payload.get("poll_token", "")).strip()
        if not code or not token:
            self._on_pair_init_result(
                {"ok": False, "error": "Ungültige Antwort von AnkiCollab erhalten."},
                attempt_id=attempt_id,
            )
            return

        self._pair_code = code
        self._pair_token = token
        url = engine.collab_pairing_url(code)
        try:
            webbrowser.open(url)
        except Exception:
            pass

        safe_code = html.escape(code)
        safe_url = html.escape(url, quote=True)
        self._status_lbl.setText(
            f"<span style='color:{COLORS['accent']};'><b>Browser geöffnet — Code:</b> "
            f"<code>{safe_code}</code><br>"
            "Bestätige die Anmeldung kurz in deinem Browser, danach geht es hier <b>automatisch</b> weiter. "
            f"<a href='{safe_url}'>Link erneut öffnen ↗</a></span>"
        )
        self._pair_poll_timer.start()
        try:
            ttl = int(payload.get("expires_in") or _PAIR_TTL_SECONDS)
        except (TypeError, ValueError):
            ttl = _PAIR_TTL_SECONDS
        self._pair_expiry_timer.start(max(10, ttl) * 1000)

    def _pair_poll_once(self) -> None:
        if self._pair_closing or not self._pair_token:
            return
        if self._pair_outstanding == self._pair_token:
            return
        self._pair_outstanding = self._pair_token

        parent = mw if isinstance(mw, QObject) else None
        worker = _PairPollWorker(self._pair_token, parent=parent)
        worker.result.connect(self._on_pair_poll_result)
        worker.start()

    def _on_pair_poll_result(self, payload: dict) -> None:
        if self._pair_closing:
            return
        if not isinstance(payload, dict) or payload.get("token") != self._pair_token:
            return
        self._pair_outstanding = ""

        outcome = payload.get("outcome")
        if outcome == "approved":
            if engine.collab_store_login_result(payload.get("body") or {}):
                cb = self._pair_then or self.next
                self._stop_pairing()
                self._record_logged_in()
                self.raise_()
                self.activateWindow()
                cb()
            else:
                self._stop_pairing()
                self._status_lbl.setText(
                    f"<span style='color:{COLORS['danger']};'>AnkiCollab-Anmeldedaten konnten nicht gespeichert werden. "
                    "Bitte versuche es erneut oder nutze das klassische Passwort-Fenster.</span>"
                )
            return

        if outcome == "rejected":
            self._stop_pairing()
            self._status_lbl.setText(
                f"<span style='color:{COLORS['warning']};'>Die Anmeldung wurde im Browser abgelehnt. "
                "Klicke einfach erneut auf <b>Jetzt mit Anki verbinden</b>.</span>"
            )
            return

        if outcome == "expired":
            self._on_pair_expired()

    def _on_pair_expired(self) -> None:
        self._stop_pairing()
        if self._pair_closing:
            return
        self._status_lbl.setText(
            f"<span style='color:{COLORS['warning']};'>Der Verbindungscode ist abgelaufen. "
            "Klicke einfach erneut auf <b>Jetzt mit Anki verbinden</b> für einen neuen Code.</span>"
        )

    def _stop_pairing(self) -> None:
        self._pair_poll_timer.stop()
        self._pair_expiry_timer.stop()
        self._pair_code = ""
        self._pair_token = ""
        self._pair_outstanding = ""
        self._pair_then = None

    def _sign_in_classic(self, then: Optional[Callable] = None) -> None:
        self._stop_pairing()
        if not engine.collab_is_logged_in():
            try:
                engine.collab_open_login(self)
            except Exception as e:
                self._status_lbl.setText(
                    f"<span style='color:{COLORS['danger']};'>Anmeldefenster konnte nicht geöffnet werden ({e}). "
                    "Öffne oben im Menü <b>AnkiCollab → Login</b> und klicke danach hier erneut auf <b>Jetzt mit Anki verbinden</b>.</span>"
                )
                return
        if engine.collab_is_logged_in():
            self._record_logged_in()
            (then or self.next)()
        else:
            self._status_lbl.setText(
                f"<span style='color:{COLORS['warning']};'>Du bist noch nicht angemeldet. Bitte bestätige die Anmeldung "
                "im Browser und klicke dann erneut auf <b>Jetzt mit Anki verbinden</b>.</span>"
            )

    # Prepare & Backup -------------------------------------------------------

    def _page_prepare(self) -> None:
        msg = (
            "<p>Bevor wir etwas umstellen, bringen wir deine Sammlung auf den neuesten Stand und "
            "erstellen eine lokale <b>Sicherheitskopie</b>. Außerdem leeren wir eventuelle Auswahlstapel "
            "und schützen deine eigenen Schlagwörter für AnkiCollab.</p>"
        )
        self._page(self._step_name("prepare"), msg)
        self._prepare()

    def _prepare(self) -> None:
        if self.info.get("ankiweb"):
            self._working("Synchronisiere zuerst mit AnkiWeb…")
            engine.sync_ankiweb(self._after_first_sync)
        else:
            self._backup()

    def _after_first_sync(self, result: str) -> None:
        if result == "error":
            self._error(
                "AnkiWeb-Sync ist fehlgeschlagen. Es wurde noch nichts verändert.",
                retry=self._prepare,
                link=("Ohne Sync fortfahren", self._backup),
            )
            return
        self.safe_to_upload = result == "ok"
        if result == "ok":
            self.summary.append("Vorher mit AnkiWeb synchronisiert")
        self._backup()

    def _backup(self) -> None:
        self._working("Erstelle Sicherheitskopie & sichere eigene Schlagwörter…")

        def op(col):
            create_backup_now(mw)
            emptied = engine.empty_ankizin_filtered_decks(col)
            personal = engine.detect_personal_tags_on_ankizin(col)
            return emptied, personal

        def succeeded(res: tuple[int, list[str]]) -> None:
            emptied, personal = res
            protected = engine.protect_personal_tags_for_collab(None, self.key, predetected_tags=personal)
            self.summary.append("Sicherheitskopie der Sammlung erstellt")
            if emptied:
                self.summary.append(f"{emptied} Auswahlstapel vor dem Umzug geleert")
            if protected:
                self.summary.append("Eigene Schlagwörter für AnkiCollab geschützt")
            self.next()

        def failed(exc: Exception) -> None:
            self._error(
                f"Sicherheitskopie fehlgeschlagen — nichts wurde verändert.<br><small>{exc}</small>",
                retry=self._backup,
            )

        QueryOp(parent=self, op=op, success=succeeded).failure(failed).with_progress(
            "Erstelle Sicherheitskopie…"
        ).run_in_background()

    # Leave AnkiHub ----------------------------------------------------------

    def _page_ankihub(self) -> None:
        self._page(
            "AnkiHub sauber trennen",
            "<p>Wir beenden die Ankizin-Synchronisation über AnkiHub, damit sich AnkiHub und AnkiCollab "
            "nicht gegenseitig überschreiben.</p>"
            "<p><b>Deine Karten und dein Lernfortschritt bleiben vollständig erhalten.</b></p>",
        )
        self._leave_ankihub()

    def _leave_ankihub(self) -> None:
        decks = engine.ankihub_ankizin_decks(self.settings)
        if not decks:
            self.next()
            return
        self._working("Trenne Ankizin von AnkiHub…")

        def unsubscribe(_):
            return [(d, engine.ankihub_unsubscribe_on_server(d["uuid"])) for d in decks]

        def remove(results) -> None:
            try:
                for deck, on_server_ok in results:
                    engine.ankihub_remove_locally(deck["uuid"])
                    if not on_server_ok:
                        self.ankihub_still_on_server.append(deck["name"])
            except Exception as e:
                self._error(
                    f"AnkiHub konnte Ankizin nicht automatisch entfernen ({e}).<br>"
                    "Öffne kurz <b>AnkiHub → Deck Management</b>, entferne Ankizin und klicke auf <b>Erneut versuchen</b>.",
                    retry=self._leave_ankihub,
                )
                return
            self.changed_notetypes = True
            if mw:
                mw.reset()
            self.summary.append("Ankizin-Abo bei AnkiHub beendet")
            self.next()

        QueryOp(parent=self, op=unsubscribe, success=remove).without_collection().failure(
            lambda e: self._error(f"Fehler beim Trennen von AnkiHub ({e}).", retry=self._leave_ankihub)
        ).run_in_background()

    # Set aside old deck -----------------------------------------------------

    def _page_aside(self) -> None:
        self._page(
            "Altes Deck beiseite legen",
            "<p>Damit AnkiCollab ein sauberes neues <b>Ankizin</b>-Deck aufbauen kann, benennen wir dein "
            "bisheriges Deck kurz um (z. B. in <code>Ankizin_alt</code>). Deine Karten samt Lernfortschritt "
            "wandern beim Download automatisch ins neue Deck.</p>",
        )
        col = mw.col if mw else None
        if col:
            for did in self.info.get("old_decks", []):
                if not col.decks.get(did, default=False):
                    continue
                new_name = engine.set_deck_aside(col, did, suffix="_alt")
                line = f"Alten Stapel sicher in „{new_name}“ umbenannt"
                self.aside_dids.append(did)
                self.aside_lines[did] = line
                self.summary.append(line)
            if mw:
                mw.reset()
        self.next()

    # Download Ankizin -------------------------------------------------------

    def _page_download(self) -> None:
        migrating = self.info["scenario"] in ("migrate_ankihub", "migrate_apkg", "dual")
        self._page(
            "Ankizin-Deck herunterladen",
            "<p>AnkiCollab lädt jetzt das offizielle <b>Ankizin-Deck</b> (Karten zuerst, Bilder danach im Hintergrund).</p>"
            "<p>Der Download dauert meist <b>2–5 Minuten</b>. Bitte lass Anki solange geöffnet.</p>"
            + (
                "<p><b>Umzug:</b> Deine vorhandenen Karten und dein Lernfortschritt werden automatisch zugeordnet.</p>"
                if migrating
                else ""
            ),
        )
        if engine.collab_installed_deck_id(self.key):
            self._downloaded()
            return
        if engine.collab_subscription(self.key) is not None:
            engine.collab_forget_subscription(self.key)
        self._start_download()

    def _start_download(self) -> None:
        if not engine.collab_is_logged_in():
            self.busy = False
            self._status_lbl.setText("AnkiCollab benötigt für den Download eine Anmeldung.")
            self._set_buttons(
                primary=("Jetzt anmelden", lambda: self._sign_in(then=self._start_download)),
                secondary=("Später", self.close),
            )
            return

        # Configure AnkiCollab per wiki BEFORE pulling so new cards start suspended
        engine.collab_configure_settings(pull_on_startup=True, suspend_new_cards=True, preserve_deck_structure=True)
        protected = engine.detect_personal_tags_on_ankizin(mw.col) if (mw and mw.col) else []
        if "AnkiCollab_Personal" not in protected:
            protected.append("AnkiCollab_Personal")

        self._working("Lade Ankizin herunter… AnkiCollab zeigt ggf. zusätzlich ein Fortschrittsfenster.")
        self._pull_finished_at = None
        try:
            engine.collab_subscribe(self.key, self._pulled, protected_extra=protected)
        except Exception as e:
            print(f"Ankizin: AnkiCollab subscribe failed: {e}")
            self._manual_subscribe_fallback()
            return
        self._poll.start(1500)

    def _pulled(self, ok: bool) -> None:
        if not ok:
            self._poll.stop()
            self._error(
                "Der Download konnte nicht abgeschlossen werden. Bitte prüfe deine Internetverbindung.",
                retry=self._retry_download,
                link=("Über AnkiCollab-Fenster manuell einfügen", self._manual_subscribe_fallback),
            )
            return
        self._pull_finished_at = time.time()

    def _poll_download(self) -> None:
        if engine.collab_installed_deck_id(self.key):
            self._poll.stop()
            self._downloaded()
            return
        if self._pull_finished_at and mw and not mw.progress.busy() and time.time() - self._pull_finished_at > 20:
            self._set_buttons(
                primary=("Erneut versuchen", self._retry_download),
                link=("Über AnkiCollab-Fenster manuell einfügen", self._manual_subscribe_fallback),
            )
            self._status_lbl.setText(
                "Der Vorgang dauert ungewöhnlich lange. Falls nichts mehr passiert, klicke auf <b>Erneut versuchen</b>."
            )
            self._pull_finished_at = None

    def _retry_download(self) -> None:
        self._poll.stop()
        engine.collab_forget_subscription(self.key)
        self._start_download()

    def _manual_subscribe_fallback(self) -> None:
        self._poll.stop()
        QApplication.clipboard().setText(self.key)
        self._page(
            "Ankizin in AnkiCollab hinzufügen",
            "<p>Der Ankizin-Schlüssel wurde bereits in deine Zwischenablage kopiert:</p>"
            + _bullets(
                [
                    "Klicke auf <b>AnkiCollab öffnen</b>",
                    "Klicke unten im Fenster in das Feld <i>Add New Subscription</i>",
                    "Füge mit <b>Strg+V</b> (Mac: <b>⌘V</b>) ein: <code>" + self.key + "</code> und klicke <b>Add Subscription</b>",
                    "Warte kurz auf den Download und klicke dann hier auf <b>Erneut prüfen</b>",
                ]
            ),
            primary=("Erneut prüfen", self._page_download_check),
            secondary=("AnkiCollab öffnen", self._open_collab_subscriptions),
        )

    def _open_collab_subscriptions(self) -> None:
        try:
            engine.collab_open_subscriptions()
        except Exception:
            self._status_lbl.setText("Öffne oben in Anki: <b>AnkiCollab → Edit Subscriptions</b>.")

    def _page_download_check(self) -> None:
        if engine.collab_installed_deck_id(self.key):
            self._downloaded()
        else:
            self._status_lbl.setText("Ankizin ist noch nicht fertig geladen. Sobald der Download durch ist, klicke erneut.")

    def _downloaded(self) -> None:
        did = engine.collab_installed_deck_id(self.key)
        col = mw.col if mw else None
        if did and col:
            reclaimed = [
                d for d in self.aside_dids
                if col.decks.get(d, default=False) and did in col.decks.deck_and_child_ids(d)
            ]
            for d in reclaimed:
                line = self.aside_lines.pop(d, None)
                if line in self.summary:
                    self.summary.remove(line)
            self.aside_dids = [d for d in self.aside_dids if d not in reclaimed]
            for old_did in self.aside_dids:
                if col.decks.get(old_did, default=False):
                    engine.copy_deck_options(col, old_did, did)
        deck_name = col.decks.name(did) if (did and col) else "Ankizin"
        self.summary.append(f"Ankizin-Deck in „{deck_name}“ installiert")
        self.next()

    # Configure Ankizin ------------------------------------------------------

    def _page_configure(self) -> None:
        migrating = self.info["scenario"] in ("migrate_ankihub", "migrate_apkg", "dual")
        self._page(
            "Ankizin optimal für dich einrichten",
            "<p>Jetzt passen wir Anki an die offiziellen Ankizin-Empfehlungen an — mit einem Klick:</p>",
            primary=("Einstellungen anwenden →", self._apply_configuration),
            secondary=("Überspringen", self.skip),
        )

        # Card 1: Suspend cards
        c1, l1 = make_card("ankizin_card_soft", padding=(12, 10, 12, 10))
        suspend_title = (
            "Alle neuen/ungelernten Ankizin-Karten pausieren (Empfohlen)"
            if migrating
            else "Alle Ankizin-Karten vorerst pausieren (Empfohlen)"
        )
        suspend_desc = (
            "Ankizin hat über 40.000 Karten! Pausierte Karten wartest du in Ruhe ab und schaltest in der "
            "<b>Ankizin Lern-Zentrale</b> immer nur das Thema frei, das du gerade lernst."
            + (" Dein bestehender Lernfortschritt bleibt dabei komplett unberührt." if migrating else "")
        )
        suspend_row, self._suspend_cb = make_wrapped_checkbox(suspend_title, suspend_desc, checked=True)
        l1.addWidget(suspend_row)
        self._extra_lay.addWidget(c1)

        # Card 2: FSRS & Daily Pace
        c2, l2 = make_card("ankizin_card_soft", padding=(12, 10, 12, 10))
        fsrs_row, self._fsrs_cb = make_wrapped_checkbox(
            "Optimale Ankizin-Lerneinstellungen (FSRS) aktivieren (Empfohlen)",
            "Aktiviert den modernen FSRS-Algorithmus, setzt 15-Minuten-Lernschritte, "
            "zeigt Wiederholungen vor neuen Karten (Max-Intervall 3600 Tage) und schützt deinen eigenen Ankizin-Preset.",
            checked=True,
        )
        l2.addWidget(fsrs_row)

        pace_hdr_row = QHBoxLayout()
        pace_hdr_row.setSpacing(8)
        pace_title_lbl = QLabel("<b>Tägliches Ziel (neue Karten):</b>")
        pace_title_lbl.setWordWrap(True)
        self._pace_hint = QLabel("Empfohlen · ≈ 320–400 Wdh./Tag")
        self._pace_hint.setStyleSheet("font-size: 12px; color: palette(placeholderText);")
        pace_hdr_row.addWidget(pace_title_lbl)
        pace_hdr_row.addWidget(self._pace_hint, 1)
        l2.addLayout(pace_hdr_row)

        pace_btn_row = QHBoxLayout()
        self._pace_seg = SegmentedControl(
            [
                ("20", "20 / Tag", "Entspannt: ca. 160–240 Wiederholungen/Tag"),
                ("40", "40 / Tag ★", "Empfohlen: ca. 320–400 Wiederholungen/Tag"),
                ("60", "60 / Tag", "Intensiv: ca. 480–600 Wiederholungen/Tag"),
            ],
            initial_key="40",
        )
        self._pace_seg.changed.connect(
            lambda k: self._pace_hint.setText(
                {
                    "20": "Entspannt · ≈ 160–240 Wdh./Tag",
                    "40": "Empfohlen · ≈ 320–400 Wdh./Tag",
                    "60": "Intensiv · ≈ 480–600 Wdh./Tag",
                }.get(k, "")
            )
        )
        pace_btn_row.addWidget(self._pace_seg)
        pace_btn_row.addStretch()
        l2.addLayout(pace_btn_row)
        self._extra_lay.addWidget(c2)

        # Card 3: Automation & Cleanup
        c3, l3 = make_card("ankizin_card_soft", padding=(12, 10, 12, 10))
        l3.addWidget(QLabel("<b>Automatische Pflege</b>"))
        sync_row, self._auto_sync_cb = make_wrapped_checkbox(
            "Beim Start automatisch nach Ankizin-Updates suchen & neue Karten pausieren",
            checked=True,
            bold_title=False,
        )
        del_row, self._delete_cb = make_wrapped_checkbox(
            "Veraltete Karten (!DELETE) & leere Karten automatisch aufräumen",
            checked=True,
            bold_title=False,
        )
        flag_row, self._flag_hy_cb = make_wrapped_checkbox(
            "High-Yield-Karten farblich markieren (Rot = Stark gelb, Orange = Leicht gelb)",
            checked=False,
            bold_title=False,
        )
        l3.addWidget(sync_row)
        l3.addWidget(del_row)
        l3.addWidget(flag_row)
        self._extra_lay.addWidget(c3)

    def _apply_configuration(self) -> None:
        migrating = self.info["scenario"] in ("migrate_ankihub", "migrate_apkg", "dual")
        per_day = int(self._pace_seg.current_key() or "40")
        opts = {
            "suspend_cards": self._suspend_cb.isChecked(),
            "suspend_only_new": migrating,
            "apply_settings": self._fsrs_cb.isChecked(),
            "new_per_day": per_day,
            "max_ivl": 3600,
            "delete_marked": self._delete_cb.isChecked(),
            "include_reviewed_deletes": False,
            "flag_high_yield": self._flag_hy_cb.isChecked(),
            "delete_empty_cards": self._delete_cb.isChecked(),
        }
        auto_sync = self._auto_sync_cb.isChecked()
        self._working("Konfiguriere dein Ankizin-Deck…")

        def op(col):
            res = engine.configure_ankizin_collection(col, opts)
            return engine.OpResult(res, res["changes"])

        def done(out: engine.OpResult) -> None:
            res = out.value
            if auto_sync:
                engine.collab_configure_settings(pull_on_startup=True, suspend_new_cards=True)
            if mw and getattr(mw, "addonManager", None):
                conf = mw.addonManager.getConfig(ADDON_DIR_NAME) or {}
                conf["auto_sync_ankicollab_on_startup"] = auto_sync
                mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)

            if res.get("suspended"):
                self.summary.append(f"{res['suspended']:,} Karten sicher pausiert".replace(",", "."))
            if res.get("settings"):
                self.summary.append(f"FSRS & Ankizin-Empfehlungen aktiviert ({per_day} neue/Tag)")
            if res.get("deleted"):
                self.summary.append(f"{res['deleted']} veraltete !DELETE-Karten entfernt")
            if res.get("flagged_stark") or res.get("flagged_leicht"):
                self.summary.append("High-Yield-Karten farblich markiert")
            engine.update_setup_state(configured=True)
            self.next()

        def fail(exc: Exception) -> None:
            self._error(f"Einrichtung fehlgeschlagen ({exc}).", retry=self._apply_configuration)

        CollectionOp(self, op).success(done).failure(fail).run_in_background()

    # Save to AnkiWeb --------------------------------------------------------

    def _page_save(self) -> None:
        if self.changed_notetypes:
            text = (
                "<p>Letzter Schritt: Durch das Trennen von AnkiHub benötigt AnkiWeb einmalig eine frische Kopie "
                "deiner Sammlung.</p>"
            )
            if self.safe_to_upload:
                text += "<p>Klicke auf <b>Jetzt synchronisieren</b> — wir laden deine Sammlung automatisch hoch.</p>"
            else:
                text += "<p>Falls Anki fragt, wähle <b>Auf AnkiWeb hochladen</b>.</p>"
            text += (
                "<p><b>Hinweis für iPad/Handy:</b> Wähle beim nächsten Sync auf deinen Mobilgeräten "
                "<b>Von AnkiWeb herunterladen</b>.</p>"
            )
        else:
            text = "<p>Synchronisiere jetzt einmal mit AnkiWeb, damit dein frisch eingerichtetes Deck auf allen Geräten bereitsteht.</p>"

        self._page(
            "Mit AnkiWeb synchronisieren",
            text,
            primary=("Jetzt synchronisieren", self._sync_after),
            link=("Später synchronisieren", self._skip_save),
        )

    def _skip_save(self) -> None:
        self.save_skipped = True
        self.skip()

    def _sync_after(self) -> None:
        self._working("Synchronisiere mit AnkiWeb…")

        def done(result: str) -> None:
            if result == "error":
                self._error(
                    "Synchronisation nicht abgeschlossen. Prüfe deine Internetverbindung.",
                    retry=self._sync_after,
                    link=("Später synchronisieren", self._skip_save),
                )
                return
            self.summary.append("Mit AnkiWeb synchronisiert")
            self.next()

        engine.sync_ankiweb(done, upload_if_asked=self.safe_to_upload)

    # Finish -----------------------------------------------------------------

    def _page_finish(self) -> None:
        engine.update_setup_state(resume=False, finished=True, configured=True)

        if self.info["scenario"] == "ready" and not self.summary:
            summary_html = "<p><b>Dein Ankizin-Deck ist bereits komplett über AnkiCollab eingerichtet!</b></p>"
        else:
            summary_html = "".join(
                f"<div style='margin-bottom:5px;'><span style='color:{COLORS['success']};font-weight:700;'>✓</span>"
                f"&nbsp; {line}</div>"
                for line in self.summary
            )

        if self.ankihub_still_on_server:
            summary_html += (
                "<p style='color:gray;'>Hinweis: Melde dich bei Gelegenheit auf "
                "<a href='https://app.ankihub.net'>app.ankihub.net</a> vom Ankizin-Deck ab, "
                "damit es dort nicht weiter als abonniert steht.</p>"
            )

        self._page(
            "Alles fertig! 🎉",
            summary_html,
            primary=("Themen auswählen & loslernen →", self._finish_and_open_hub),
            secondary=("Fertig", self.accept),
            link=("Lerneinstellungen anpassen", self._reconfigure_from_finish) if self.info["scenario"] == "ready" else None,
        )

        # Beginner quick-start card
        guide_card, guide_lay = make_card("ankizin_card_accent")
        guide_lay.addWidget(QLabel("<b>So lernst du ab jetzt in 2 Schritten — ganz ohne Kartenverwaltung:</b>"))
        tips = QLabel(
            "1. Öffne die <b>Ankizin Lern-Zentrale</b>, suche dein aktuelles Thema (z. B. Kardiologie oder Lerntag 01) "
            "und schalte nur die Karten frei, die du lernen möchtest.<br>"
            "2. Beim Abfragen genügen fast immer die Buttons <b>Nochmal</b> (nicht gewusst) und <b>Gut</b> (gewusst)."
        )
        tips.setWordWrap(True)
        guide_lay.addWidget(tips)
        self._extra_lay.addWidget(guide_card)

        self._add_old_deck_rows()

    def _add_old_deck_rows(self) -> None:
        col = mw.col if mw else None
        if not col or not self.aside_dids:
            return
        rows = []
        for did in self.aside_dids:
            if not col.decks.get(did, default=False):
                continue
            name = col.decks.name(did)
            cnt = engine.deck_card_count(col, did)
            if cnt:
                text = (
                    f"<b>„{name}“</b> enthält noch {cnt:,} Karten (z. B. eigene Karten oder gelöschte Altkarten). "
                    "Sie wurden zur Sicherheit nicht gelöscht."
                ).replace(",", ".")
                rows.append((did, text, True, name))
            else:
                text = f"<b>„{name}“</b> ist jetzt leer — alle Karten sind umgezogen."
                rows.append((did, text, False, name))
        if not rows:
            return

        heading = QLabel("<b>Dein alter Ankizin-Stapel</b>")
        self._extra_lay.addWidget(heading)
        for did, text, has_cards, name in rows:
            row = QHBoxLayout()
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            row.addWidget(lbl, 1)
            btn = QPushButton("Karten ansehen" if has_cards else "Leeren Stapel löschen")
            btn.setObjectName("secondary")
            btn.setAutoDefault(False)
            if has_cards:
                btn.clicked.connect(lambda _=False, n=name: self._browse_deck(n))
            else:
                btn.clicked.connect(lambda _=False, d=did, b=btn, l=lbl: self._delete_empty(d, b, l))
            row.addWidget(btn)
            self._extra_lay.addLayout(row)

    def _browse_deck(self, name: str) -> None:
        from aqt import dialogs
        browser = dialogs.open("Browser", mw)
        escaped = name.replace('"', '\\"')
        browser.search_for(f'"deck:{escaped}"')

    def _delete_empty(self, did: int, btn: QPushButton, lbl: QLabel) -> None:
        col = mw.col if mw else None
        if not col or not col.decks.get(did, default=False):
            return
        if engine.deck_card_count(col, did):
            btn.setEnabled(False)
            return
        name = col.decks.name(did)
        col.decks.remove([did])
        if mw:
            mw.reset()
        lbl.setText(f"Leerer Stapel „{name}“ wurde gelöscht.")
        btn.setEnabled(False)
        btn.setText("Gelöscht")

    def _reconfigure_from_finish(self) -> None:
        if "configure" not in self.plan:
            idx = self.plan.index("finish") if "finish" in self.plan else len(self.plan)
            self.plan.insert(idx, "configure")
        self.done_steps.discard("finish")
        self.go("configure")

    def _finish_and_open_hub(self) -> None:
        self.accept()
        from ..study_hub.dialog import open_study_hub
        open_study_hub()

    def _on_closed(self, _result: int) -> None:
        self._pair_closing = True
        self._stop_pairing()
        self._poll.stop()
        if self.current == "download" and self.busy:
            tooltip("AnkiCollab lädt Ankizin im Hintergrund weiter herunter.", parent=mw, period=5000)
        elif self.current not in ("finish", "welcome"):
            tooltip(
                "Du kannst die Einrichtung jederzeit unter Ankizin → Einrichtungs-Assistent fortsetzen.",
                parent=mw,
                period=5000,
            )

    def closeEvent(self, event) -> None:
        self._pair_closing = True
        self._stop_pairing()
        super().closeEvent(event)


def open_setup_wizard(resumed: bool = False, force: bool = False) -> None:
    global _wizard
    if _wizard is not None:
        try:
            if _wizard.isVisible():
                _wizard.raise_()
                _wizard.activateWindow()
                return
        except RuntimeError:
            pass
    _wizard = AnkizinSetupWizard(mw, resumed=resumed)
    _wizard.show()


def _ask_onboarding_dialog(title: str, body_html: str, go_label: str, allow_never: bool = True) -> str:
    """Friendly branded prompt returning 'go' | 'later' | 'never'."""
    dlg = QDialog(mw)
    dlg.setWindowTitle("Ankizin")
    apply_ankizin_style(dlg)
    dlg.setMinimumWidth(480)
    choice = {"val": "later"}

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(0, 0, 0, 14)
    lay.addWidget(make_header("Ankizin", "Medizin gemeinsam lernen"))

    inner = QVBoxLayout()
    inner.setContentsMargins(20, 14, 20, 4)
    inner.setSpacing(10)

    h = QLabel(title)
    h.setWordWrap(True)
    h.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {COLORS['accent']};")
    inner.addWidget(h)

    b = QLabel(body_html)
    b.setWordWrap(True)
    b.setTextFormat(Qt.TextFormat.RichText)
    inner.addWidget(b)

    row = QHBoxLayout()
    if allow_never:
        never_lbl = QLabel("<a href='#' style='color:gray;text-decoration:none;'>Nicht mehr fragen</a>")
        never_lbl.linkActivated.connect(lambda _=None: (choice.update(val="never"), dlg.reject()))
        row.addWidget(never_lbl)
    row.addStretch()
    later_btn = QPushButton("Später")
    later_btn.setObjectName("secondary")
    later_btn.clicked.connect(dlg.reject)
    go_btn = QPushButton(go_label)
    go_btn.clicked.connect(lambda: (choice.update(val="go"), dlg.accept()))
    row.addWidget(later_btn)
    row.addWidget(go_btn)
    inner.addSpacing(4)
    inner.addLayout(row)
    lay.addLayout(inner)

    disable_auto_default(dlg, go_btn)
    dlg.exec()
    return choice["val"]


def maybe_prompt_onboarding_on_startup() -> bool:
    """Check onboarding status on startup. Returns True if wizard/prompt took over."""
    if mw is None or not getattr(mw, "col", None):
        return False

    state = engine.get_setup_state()
    if state.get("resume"):
        engine.update_setup_state(resume=False)
        open_setup_wizard(resumed=True)
        return True

    info = engine.detect_setup_state()
    scenario = info["scenario"]
    if scenario == "ready":
        return False

    now = time.time()
    if scenario != "dual" and state.get("never_ask"):
        return False
    if now < float(state.get("snooze_until", 0) or 0):
        return False

    prompts = {
        "new": (
            "Ankizin automatisch einrichten?",
            "<p>Du hast das Ankizin-Add-on installiert! Unser Assistent richtet jetzt in wenigen Klicks "
            "<b>AnkiCollab</b>, das komplette <b>Ankizin-Deck</b> und die <b>optimalen FSRS-Einstellungen</b> für dich ein.</p>",
            "Jetzt einrichten",
            True,
        ),
        "migrate_ankihub": (
            "Ankizin ist zu AnkiCollab umgezogen",
            "<p>Wir können dein bestehendes Ankizin-Deck in wenigen Klicks automatisch von AnkiHub auf das "
            "kostenlose <b>AnkiCollab</b> umziehen. <b>Dein kompletter Lernfortschritt bleibt erhalten.</b></p>",
            "Deck jetzt umziehen",
            True,
        ),
        "migrate_apkg": (
            "Ankizin mit AnkiCollab verbinden?",
            "<p>Du nutzt bereits eine Ankizin-Version. Verbinde dein Deck jetzt kostenlos mit <b>AnkiCollab</b>, "
            "um automatisch neue Karten und Korrekturen zu erhalten — ohne Verlust deines Lernfortschritts.</p>",
            "Jetzt verbinden",
            True,
        ),
        "dual": (
            "Ankizin ist doppelt verbunden",
            "<p>AnkiHub und AnkiCollab aktualisieren gleichzeitig dein Ankizin-Deck — das kann zu Konflikten führen. "
            "Wir lösen das sauber in wenigen Sekunden für dich, ohne deinen Lernfortschritt anzutasten.</p>",
            "Konflikt jetzt lösen",
            False,
        ),
        "incomplete": (
            "Ankizin-Einrichtung abschließen",
            "<p>Deine Ankizin-Einrichtung ist noch nicht ganz abgeschlossen (z. B. AnkiCollab-Anmeldung oder Lerneinstellungen).</p>",
            "Einrichtung fortsetzen",
            True,
        ),
    }
    title, body, go_label, allow_never = prompts[scenario]
    answer = _ask_onboarding_dialog(title, body, go_label, allow_never=allow_never)
    if answer == "go":
        open_setup_wizard()
    elif answer == "never":
        engine.update_setup_state(never_ask=True)
    else:
        engine.update_setup_state(snooze_until=now + (1 if scenario == "dual" else 3) * DAY_SECS)
    return True
