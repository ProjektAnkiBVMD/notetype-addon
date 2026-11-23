"""Theme-adaptive Home Screen Quick-Bar and Onboarding Banner for Ankizin."""
from __future__ import annotations

import html
from typing import Any

from aqt import mw

from ..constants import ADDON_DIR_NAME
from ..onboarding import engine
from ..onboarding.maintenance import get_pending_reviewed_deletes

_CSS = """
<style>
.ankizin-home-card {
  margin: 14px auto 0;
  max-width: 42em;
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid rgba(59, 130, 214, 0.34);
  background: rgba(59, 130, 214, 0.08);
  text-align: left;
  font-size: 13px;
  box-sizing: border-box;
}
.ankizin-home-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.ankizin-home-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.ankizin-btn-primary {
  display: inline-block;
  padding: 7px 14px;
  border-radius: 8px;
  background: #3B82D6;
  color: #ffffff !important;
  font-weight: 600;
  text-decoration: none;
  font-size: 13px;
}
.ankizin-btn-primary:hover { background: #2B6BB8; }
.ankizin-btn-secondary {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid rgba(128, 128, 128, 0.35);
  color: inherit !important;
  font-weight: 600;
  text-decoration: none;
  font-size: 12px;
}
.ankizin-btn-secondary:hover { background: rgba(59, 130, 214, 0.12); }
.ankizin-pill-ok {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(46, 158, 91, 0.16);
  color: #2E9E5B !important;
  font-weight: 600;
  font-size: 12px;
  text-decoration: none;
}
.ankizin-pill-warn {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(217, 119, 6, 0.18);
  color: #D97706 !important;
  font-weight: 600;
  font-size: 12px;
  text-decoration: none;
}
.ankizin-link-muted {
  color: gray !important;
  font-size: 12px;
  text-decoration: none;
}
</style>
"""


def render_home_banner_html(
    info: dict[str, Any],
    setup_state: dict[str, Any],
    conf: dict[str, Any],
    pending_deletes: int = 0,
) -> str:
    """Pure HTML generator for the Deck Browser Quick-Bar / Onboarding Banner."""
    scenario = info.get("scenario", "new")

    if scenario != "ready":
        if setup_state.get("dismissed_home_banner"):
            return ""
        copy_map = {
            "new": (
                "Willkommen bei Ankizin!",
                "Richte AnkiCollab, das Ankizin-Deck &amp; optimale FSRS-Einstellungen automatisch ein.",
                "Jetzt einrichten",
            ),
            "migrate_ankihub": (
                "Ankizin ist zu AnkiCollab umgezogen",
                "Ziehe dein Deck automatisch um — dein kompletter Lernfortschritt bleibt erhalten.",
                "Umzug starten",
            ),
            "migrate_apkg": (
                "Automatische Updates aktivieren",
                "Verbinde dein Ankizin-Deck kostenlos mit AnkiCollab — ohne Fortschrittsverlust.",
                "Jetzt verbinden",
            ),
            "dual": (
                "AnkiHub &amp; AnkiCollab gleichzeitig aktiv",
                "Behebe den Konflikt mit einem Klick, bevor Karten überschrieben werden.",
                "Konflikt beheben",
            ),
            "incomplete": (
                "Ankizin-Einrichtung abschließen",
                "Es fehlt nur noch ein kurzer Schritt (z. B. AnkiCollab-Anmeldung oder Lerneinstellungen).",
                "Fortsetzen",
            ),
        }
        title, subtitle, cta = copy_map.get(scenario, copy_map["new"])
        dismiss_html = (
            ""
            if scenario == "dual"
            else '<a class="ankizin-link-muted" href="#" onclick="pycmd(\'ankizin:dismiss_banner\');return false;">Ausblenden</a>'
        )
        return (
            _CSS
            + '<div class="ankizin-home-card">'
            + f'<div style="font-weight:700;font-size:14px;color:#3B82D6;margin-bottom:4px;">★ {title}</div>'
            + f'<div style="opacity:0.9;margin-bottom:10px;">{subtitle}</div>'
            + '<div class="ankizin-home-row">'
            + f'<a class="ankizin-btn-primary" href="#" onclick="pycmd(\'ankizin:open_wizard\');return false;">{html.escape(cta)} →</a>'
            + dismiss_html
            + "</div></div>"
        )

    if not conf.get("show_home_quickbar", True):
        return ""

    if pending_deletes > 0:
        status_pill = (
            f'<a class="ankizin-pill-warn" href="#" onclick="pycmd(\'ankizin:open_maintenance\');return false;">'
            f'!DELETE prüfen ({pending_deletes})</a>'
        )
    elif info.get("collab_logged_in"):
        status_pill = (
            '<a class="ankizin-pill-ok" href="#" onclick="pycmd(\'ankizin:open_maintenance\');return false;">'
            'AnkiCollab aktiv ✓</a>'
        )
    else:
        status_pill = (
            '<a class="ankizin-pill-warn" href="#" onclick="pycmd(\'ankizin:open_wizard\');return false;">'
            'AnkiCollab anmelden</a>'
        )

    return (
        _CSS
        + '<div class="ankizin-home-card">'
        + '<div class="ankizin-home-row">'
        + '<div class="ankizin-home-actions">'
        + '<a class="ankizin-btn-primary" href="#" onclick="pycmd(\'ankizin:open_hub\');return false;">✨ Themen &amp; Karten wählen</a>'
        + '<a class="ankizin-btn-secondary" href="#" onclick="pycmd(\'ankizin:open_lernplan\');return false;">📅 Lernplan</a>'
        + "</div>"
        + status_pill
        + "</div></div>"
    )


def deck_browser_ankizin_hk(_deck_browser, content) -> None:
    try:
        if mw is None or not getattr(mw, "col", None):
            return
        conf = (mw.addonManager.getConfig(ADDON_DIR_NAME) or {}) if getattr(mw, "addonManager", None) else {}
        info = engine.detect_setup_state()
        state = engine.get_setup_state()
        snippet = render_home_banner_html(
            info=info,
            setup_state=state,
            conf=conf,
            pending_deletes=get_pending_reviewed_deletes(),
        )
        if snippet:
            content.stats += snippet
    except Exception as e:
        print(f"Ankizin: home dashboard render failed: {e}")


def on_webview_js_message(handled: tuple[bool, Any], message: str, _context) -> tuple[bool, Any]:
    if not isinstance(message, str) or not message.startswith("ankizin:"):
        return handled

    cmd = message.split(":", 1)[1]
    if cmd == "open_hub":
        from ..study_hub.dialog import open_study_hub
        open_study_hub()
    elif cmd == "open_wizard":
        from ..onboarding.wizard import open_setup_wizard
        open_setup_wizard(force=True)
    elif cmd == "open_lernplan":
        from ..butler.lernplan_manager import open_lernplan_manager
        open_lernplan_manager()
    elif cmd == "open_maintenance":
        from ..onboarding.maintenance import open_maintenance_dialog
        open_maintenance_dialog()
    elif cmd == "dismiss_banner":
        engine.update_setup_state(dismissed_home_banner=True)
        if mw and getattr(mw, "deckBrowser", None):
            mw.deckBrowser.refresh()
    return (True, None)
