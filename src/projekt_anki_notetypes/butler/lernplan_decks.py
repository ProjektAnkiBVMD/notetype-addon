"""Deck-building logic of the Lernplan-Manager.

Depends on `anki` only (no `aqt`), so it can run on a worker thread inside a
`CollectionOp` as well as synchronously from the startup hooks.
"""
import datetime
import re
from dataclasses import dataclass, field

from anki.collection import Collection, OpChanges
from anki.decks import FilteredDeckConfig
from anki.errors import AnkiError

FILTERED_LIMIT = 99999  # maximum of the Qt filtered deck dialog
ORDER_ADDED = 5  # FilteredSearchOrder.ADDED, so cards are chronological (usually)

LERNTAG_PREFIX = "!LERNTAG "
DUE_DECK_NAME = "!FÄLLIGE KARTEN VERGANGENER LERNTAGE"
PREVIOUS_PARENT = "!VORHERIGE LERNTAGE"

_ROOT = "#Ankizin_*::#M2_M3_Klinik::#AMBOSS"
_TOP100_TAG = f"{_ROOT}::M2-TOP100-Themen"
_LERNTAG_LIST_RE = re.compile(
    r"#Ankizin_v(?:\d+|Ankihub|AnkiCollab)(?:::[^:]+)*::M2_Lerntag_(\d{3})_(.+)$"
)
_YIELD_ROOT = "#Ankizin_*::!MARKIERE_DIESE_KARTEN"


def effective_today(col: Collection) -> datetime.date:
    """Calendar date of the current scheduler day (respects rollover, DST)."""
    # noon of the scheduler day is safely inside it, whatever the rollover hour
    return datetime.datetime.fromtimestamp(col.sched.day_cutoff - 12 * 3600).date()


def get_lerntag_list(col: Collection) -> list[tuple[str, str]]:
    """Return sorted (number_str, topic_str) for all Lerntag tags."""
    unique: dict[str, str] = {}
    for tag in col.tags.all():
        match = _LERNTAG_LIST_RE.match(tag)
        if match:
            unique.setdefault(match.group(1), match.group(2))
    return sorted(unique.items(), key=lambda x: int(x[0]))


def update_past_days(prev_lerntag, new_lerntag, conf: dict) -> None:
    """Mark the day being left (prev_lerntag) as past in conf['lernplan']['past_days']."""
    if not prev_lerntag or int(prev_lerntag) == int(new_lerntag):
        return
    past_days = conf.setdefault("lernplan", {}).setdefault("past_days", [])
    idx = int(prev_lerntag)
    past_days.extend([False] * (idx + 1 - len(past_days)))
    past_days[idx] = True


@dataclass
class LerntagSettings:
    lerntag: str  # zero-padded, e.g. "005"
    highyield_stark: bool = False
    highyield_leicht: bool = False
    lowyield: bool = False
    top100: bool = False
    subchapters: bool = False

    @classmethod
    def from_conf(cls, conf: dict) -> "LerntagSettings":
        # legacy configs only have a single "highyield" flag
        legacy = conf.get("highyield", False)
        return cls(
            lerntag=str(conf.get("lerntag", "001")).zfill(3),
            highyield_stark=conf.get("highyield_stark", legacy),
            highyield_leicht=conf.get("highyield_leicht", legacy),
            lowyield=conf.get("lowyield", False),
            top100=conf.get("top100", False),
            subchapters=conf.get("create_subchapter_decks", False),
        )

    def to_conf(self) -> dict:
        return {
            "lerntag": self.lerntag,
            "highyield_stark": self.highyield_stark,
            "highyield_leicht": self.highyield_leicht,
            "highyield": None,
            "normyield": not (self.highyield_stark or self.lowyield),
            "lowyield": self.lowyield,
            "top100": self.top100,
            "create_subchapter_decks": self.subchapters,
        }


@dataclass
class DeckResult:
    skipped: list[str] = field(default_factory=list)  # decks without cards
    failed: list[tuple[str, str]] = field(default_factory=list)  # (deck, message)
    changes: OpChanges = field(default_factory=OpChanges)


def _esc(text: str) -> str:
    """Escape Anki search syntax so `text` matches literally inside a quoted term."""
    return (
        text.replace("\\", "\\\\").replace('"', r"\"").replace("*", r"\*").replace("_", r"\_")
    )


# Only the version wildcard `Ankizin_*` stays a wildcard, everything else is literal.
_LERNTAG_TAG = "#Ankizin_*::" + _esc("#M2_M3_Klinik::#AMBOSS::M2-100-Tage-Lernplan::M2_Lerntag_")


def _tag_term(literal: str, wildcard_suffix: str = "") -> str:
    return f'"tag:{_LERNTAG_TAG}{_esc(literal)}{wildcard_suffix}"'


def _yield_search(s: LerntagSettings) -> str:
    if s.highyield_stark:
        tags = [
            f"{_YIELD_ROOT}::M2_high_yield_(IMPP-Relevanz)::stark_gelb_M2",
            f"{_YIELD_ROOT}::M2_IMPP-Relevanz_(yield)::01-*",
        ]
        if s.highyield_leicht:
            tags += [
                f"{_YIELD_ROOT}::M2_high_yield_(IMPP-Relevanz)::leicht_gelb_M2",
                f"{_YIELD_ROOT}::M2_IMPP-Relevanz_(yield)::02-*",
            ]
        return " (" + " OR ".join(f'"tag:{t}"' for t in tags) + ")"
    if not s.lowyield:
        tags = [
            f"{_YIELD_ROOT}::M2_low_yield",
            f"{_YIELD_ROOT}::M2_IMPP-Relevanz_(yield)::04-*",
        ]
        return " -(" + " OR ".join(f'"tag:{t}"' for t in tags) + ")"
    return ""


def _filters(s: LerntagSettings) -> str:
    return (f' "tag:{_TOP100_TAG}"' if s.top100 else "") + _yield_search(s)


def _name_suffix(s: LerntagSettings) -> str:
    out = " - TOP-100" if s.top100 else ""
    if s.highyield_stark:
        out += " - high-yield (alle)" if s.highyield_leicht else " - high-yield (stark gelb)"
    elif s.lowyield:
        out += " - inkl. low-yield"
    return out


def _subchapter_pairs(col: Collection, lerntag: str) -> list[tuple[str, str]]:
    """(chapter, subchapter) of a Lerntag; deeper tag levels are covered by their parent."""
    pattern = re.compile(
        rf"#Ankizin_[^:]+::#M2_M3_Klinik::#AMBOSS::M2-100-Tage-Lernplan::M2_Lerntag_{lerntag}_([^:]+)::([^:]+)(?:::.*)?$"
    )
    pairs = {m.groups() for m in map(pattern.match, col.tags.all()) if m}
    return sorted(pairs)


def _lerntag_specs(
    col: Collection,
    s: LerntagSettings,
    lerntag: str,
    prefix: str,
    parent: str | None = None,
    unsuspend: bool = False,
) -> list[tuple]:
    base = f"{prefix}{lerntag}"
    suffix = _name_suffix(s)
    pairs = _subchapter_pairs(col, lerntag) if s.subchapters else []

    def spec(term: str, name: str) -> tuple:
        search = col.build_search_string(term) + _filters(s)
        return (f"{parent}::{name}" if parent else name, search, unsuspend)

    if not pairs:
        # trailing `*`: the topic name follows the number
        return [spec(_tag_term(f"{lerntag}_", "*"), base + suffix)]
    return [
        spec(
            _tag_term(f"{lerntag}_{chapter}::{sub}"),
            f"{base} - {chapter.replace('_', ' ')}{suffix}::{sub.replace('_', ' ')}",
        )
        for chapter, sub in pairs
    ]


def _due_spec(col: Collection, s: LerntagSettings, past_days) -> tuple | None:
    if int(s.lerntag) < 2:
        return None  # due cards only make sense if there is a past Lerntag
    days = "|".join(str(i).zfill(3) for i in range(1, len(past_days)) if past_days[i])
    if not days:
        return None
    pattern = f"#Ankizin_(.*?)::#M2_M3_Klinik::#AMBOSS::M2-100-Tage-Lernplan::M2_Lerntag_({days})"
    search = col.build_search_string(f'is:due "tag:re:{pattern}"') + _filters(s) + " -is:suspended"
    return (DUE_DECK_NAME, search, False)


def build_specs(
    col: Collection,
    s: LerntagSettings,
    *,
    prefix: str = LERNTAG_PREFIX,
    current: bool = True,
    previous: bool = False,
    due: bool = False,
    past_days=(),
) -> list[tuple]:
    # Order matters: a card can only be in one filtered deck, the first build wins.
    specs: list[tuple] = []
    if current:
        specs += _lerntag_specs(col, s, s.lerntag, prefix, unsuspend=True)
    if previous:
        days = [i for i in range(1, int(s.lerntag)) if i < len(past_days) and past_days[i]]
        for i in reversed(days):
            specs += _lerntag_specs(col, s, str(i).zfill(3), LERNTAG_PREFIX, parent=PREVIOUS_PARENT)
    if due and (spec := _due_spec(col, s, past_days)):
        specs.append(spec)
    return specs


def _is_managed(name: str) -> bool:
    return name.startswith(LERNTAG_PREFIX) or name == DUE_DECK_NAME or (
        name == PREVIOUS_PARENT or name.startswith(PREVIOUS_PARENT + "::")
    )


def remove_managed_decks(col: Collection) -> None:
    """Remove our filtered decks, then the empty normal parents they leave behind."""
    decks = [d for d in col.decks.all_names_and_ids() if _is_managed(d.name)]
    filtered = [d.id for d in decks if col.decks.is_filtered(d.id)]
    col.decks.remove(filtered)

    # Removing a normal deck DELETES its cards, so only remove provably empty parents.
    # Deepest first, so a parent is checked after its children are gone.
    parents = [d for d in decks if d.id not in filtered]
    for d in sorted(parents, key=lambda d: d.name.count("::"), reverse=True):
        if not col.decks.children(d.id) and col.decks.card_count(d.id, include_subdecks=False) == 0:
            col.decks.remove([d.id])


def _apply_spec(col: Collection, name: str, search: str) -> bool:
    """Create or update one filtered deck. False if the search matches no cards."""
    did = col.decks.id_for_name(name)
    if did:
        if not col.decks.is_filtered(did):
            raise AnkiError("Es existiert bereits ein normaler Stapel mit diesem Namen.")
        col.sched.empty_filtered_deck(did)  # its own cards would hide from the check below
    # same implicit exclusions as Anki's filtered deck builder
    if not col.find_cards(f"({search}) -is:suspended -is:buried -deck:filtered"):
        return False

    deck = col.sched.get_or_create_filtered_deck(did or 0)
    deck.name = name
    config = deck.config
    config.reschedule = True
    del config.delays[:]  # v1 scheduler relict
    del config.search_terms[:]
    config.search_terms.append(
        FilteredDeckConfig.SearchTerm(search=search, limit=FILTERED_LIMIT, order=ORDER_ADDED)
    )
    col.sched.add_or_update_filtered_deck(deck)
    return True


def create_filtered_decks(col: Collection, specs: list[tuple], cleanup: bool = False) -> DeckResult:
    """Create (or update) filtered decks from (name, search, unsuspend) as ONE undoable step."""
    target = col.add_custom_undo_entry("Auswahlstapel erstellen")
    result = DeckResult()
    if cleanup:
        remove_managed_decks(col)

    cids = {c for _, search, unsuspend in specs if unsuspend for c in col.find_cards(search)}
    if cids:
        col.sched.unsuspend_cards(list(cids))  # suspended cards can't enter a filtered deck

    for name, search, _ in specs:
        try:
            if not _apply_spec(col, name, search):
                result.skipped.append(name)
        except AnkiError as e:
            result.failed.append((name, str(e)))

    result.changes = col.merge_undo_entries(target)
    return result


def rebuild_lernplan_decks(
    col: Collection,
    settings: LerntagSettings,
    *,
    prefix: str = LERNTAG_PREFIX,
    cleanup: bool = False,
    current: bool = True,
    previous: bool = False,
    due: bool = False,
    past_days=(),
) -> DeckResult:
    specs = build_specs(
        col, settings, prefix=prefix, current=current, previous=previous, due=due, past_days=past_days
    )
    return create_filtered_decks(col, specs, cleanup)
