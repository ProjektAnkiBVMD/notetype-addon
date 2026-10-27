"""iCalendar export of the Lernplan (no `anki`/`aqt` imports).

Based on "Ankizin-Lernplan Plus" by Lukas Schaffner.
"""
import datetime


def _escape(text: str) -> str:
    for char in ("\\", ";", ","):
        text = text.replace(char, "\\" + char)
    return text.replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines are at most 75 octets, continuation lines start with a space."""
    out, current = [], ""
    for char in line:
        if len((current + char).encode()) > (75 if not out else 74):
            out.append(current)
            current = ""
        current += char
    return "\r\n ".join(out + [current])


def build_ics(
    schedule: list[tuple[str, datetime.date]],
    topics: dict[str, str],
    m2_date: datetime.date | None = None,
    now: datetime.datetime | None = None,
) -> str:
    """All-day events, one per Lerntag. The UIDs are stable per Lerntag and SEQUENCE grows with every
    export, so importing again updates the existing events instead of duplicating them."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    sequence = int(now.timestamp())
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Projekt Anki//Lernplan-Manager//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Ankizin Lernplan",
    ]

    def add_event(uid: str, date: datetime.date, summary: str) -> None:
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"SEQUENCE:{sequence}",
            f"DTSTART;VALUE=DATE:{date:%Y%m%d}",
            f"DTEND;VALUE=DATE:{date + datetime.timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(summary)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ])

    for number, date in schedule:
        topic = topics.get(number, "")
        add_event(f"lernplan-tag-{number}@projekt-anki", date, f"📚 Lerntag {number}" + (f": {topic}" if topic else ""))
    if m2_date:
        add_event("lernplan-m2@projekt-anki", m2_date, "🎓 M2-Examen (Tag 1)")

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
