"""Progress of the Lernplan on the Anki home screen.

Based on "Ankizin-Lernplan Plus" by Lukas Schaffner.
"""
import datetime
import html

from aqt import mw

from ..constants import ADDON_DIR_NAME
from .lernplan_decks import (
    effective_today,
    get_kreuzen_tage,
    get_lerntag_order,
    get_lerntag_topics,
    is_past_day,
    kreuzen_count,
)
from .lernplan_schedule import (
    DEFAULT_WOCHENTAGE,
    compute_schedule,
    finish_date,
    parse_date,
    parse_dates,
    remaining_lerntage,
)

GRID_COLUMNS = 20
_DONE, _CURRENT, _OPEN, _KREUZEN = "#43a047", "#fb8c00", "#616161", "#7e57c2"


def progress_grid_html(
    order: list[str], finished: set[str], current: str, topics: dict[str, str], kreuzen: set[str] = frozenset()
) -> str:
    """One colored cell per Lerntag in the user's order: current, finished, open or a Kreuzen-Tag."""
    cells = []
    for number in order:
        color = _CURRENT if number == current else _DONE if number in finished else _KREUZEN if number in kreuzen else _OPEN
        cells.append(
            f'<td bgcolor="{color}" align="center" width="24" title="{number} - {html.escape(topics.get(number, ""))}">'
            f'<font color="#ffffff">{int(number):02d}</font></td>'
        )
    rows = ("<tr>" + "".join(cells[i : i + GRID_COLUMNS]) + "</tr>" for i in range(0, len(cells), GRID_COLUMNS))
    return '<table cellspacing="2" cellpadding="2">' + "".join(rows) + "</table>"


def summary_lines(done: int, total: int, finish: datetime.date | None, m2: datetime.date | None) -> list[str]:
    """Progress, projected end and the buffer to the M2 exam."""
    lines = [f"{done}/{total} gelernt ({done * 100 // max(total, 1)}%)"]
    if finish is None:
        lines.append("Kein Lerntag ausgewählt – so wird das nichts 😉")
    elif done < total:
        lines.append(f"Plan-Ende voraussichtlich {finish:%d.%m.%Y}")
        if m2:
            buffer = (m2 - finish).days
            lines.append(f"✅ {buffer} Puffertage bis zum M2" if buffer >= 0 else f"⚠️ {-buffer} Tage hinter dem Plan")
    return lines


def deck_browser_progress_hk(deck_browser, content) -> None:
    try:
        conf = (mw.addonManager.getConfig(ADDON_DIR_NAME) or {}).get("lernplan", {})
        order = get_lerntag_order(mw.col, conf)
        if not conf.get("autocreate") or not conf.get("lerntag") or not order:
            return
        count = kreuzen_count(conf)
        topics = get_lerntag_topics(mw.col, count)
        current = str(conf["lerntag"]).zfill(3)
        finished = {n for n in order if is_past_day(conf.get("past_days", []), int(n))}

        today = effective_today(mw.col)
        schedule = compute_schedule(
            remaining_lerntage(order, current, finished),
            today,
            conf.get("wochentage", DEFAULT_WOCHENTAGE),
            parse_dates(conf.get("extra_days")),
            parse_dates(conf.get("skip_days")),
        )
        finish = finish_date(schedule, today)
        m2 = parse_date(conf.get("m2_date"))

        pct = len(finished) * 100 // len(order)
        behind = bool(m2 and finish and m2 < finish)
        title = "🎉 Lernplan abgeschlossen!" if len(finished) >= len(order) else f"Lerntag {current}"
        if current in topics:
            title += f" – {html.escape(topics[current])}"
        info = " &nbsp;·&nbsp; ".join(summary_lines(len(finished), len(order), finish, m2))
        content.stats += (
            '<div style="margin:1.5em auto 0;max-width:42em;padding:12px 16px;border:1px solid #8884;'
            'border-radius:10px;text-align:left;font-size:14px;">'
            '<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;">'
            f"<b>📚 Lernplan</b><span>{title}</span></div>"
            '<div style="background:rgba(128,128,128,.25);border-radius:6px;height:12px;margin:8px 0;overflow:hidden;">'
            f'<div style="width:{pct}%;background:{"#e53935" if behind else _DONE};height:100%;"></div></div>'
            f'<div style="opacity:.85;">{info}</div>'
            f'<div style="margin-top:8px;">{progress_grid_html(order, finished, current, topics, set(get_kreuzen_tage(mw.col, count)))}</div></div>'
        )
    except Exception as e:
        # the home screen must never break because of the progress display
        print(f"Ankizin: Lernplan progress could not be shown: {e}")
