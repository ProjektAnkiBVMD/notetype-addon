"""Fast Ankizin Tag Indexer, Search Engine, and Card Previewer.

Turns Ankizin's deep `#Ankizin_v...::...` tag hierarchy into clean German
categories and searchable topics without ever requiring the user to understand
Anki tags or search syntax. Depends only on `anki`, so all logic is directly
unit-testable against real temporary collections.
"""
from __future__ import annotations

import html as _html
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from anki.collection import Collection

# ── Yield & Flag Bitmasks ────────────────────────────────────────────────────

YIELD_STARK = 1
YIELD_LEICHT = 2
YIELD_STANDARD = 4
YIELD_LOW = 8

YIELD_ALL = YIELD_STARK | YIELD_LEICHT | YIELD_STANDARD | YIELD_LOW
YIELD_HIGH = YIELD_STARK | YIELD_LEICHT

YIELD_PRESETS = {
    "stark": YIELD_STARK,
    "high_yield": YIELD_HIGH,
    "standard": YIELD_STARK | YIELD_LEICHT | YIELD_STANDARD,
    "all": YIELD_ALL,
}

FLAG_TOP100 = 1
FLAG_MERKE = 2
FLAG_AERZTLICH = 4
FLAG_ZAHNI = 8

CATEGORIES: list[tuple[str, str, str]] = [
    ("amboss", "📚 AMBOSS", "Kapitel & Artikel aus der AMBOSS-Klinik-Bibliothek"),
    ("lernplan", "🎯 100-Tage-Plan", "M2 100-Tage-Lernplan Tag für Tag"),
    ("top100", "⭐ TOP-100", "Die 100 wichtigsten Kapitel für das M2"),
    ("m3", "🩺 M3", "Mündlich-praktische Prüfung & Kenntnisprüfung"),
    ("vorklinik", "🧬 Vorklinik", "Vorklinische Fächer & Physikum"),
    ("unis", "🏛️ Unis", "Lokale Uni-Curricula & Semester"),
]

_ALLOWED_CATEGORIES = {k for k, _, _ in CATEGORIES}

_ROOT_RE = re.compile(r"^#(?:Ankizin_[^:]+|Zankiphil)::(.+)$", re.IGNORECASE)
_LERNTAG_RE = re.compile(r"^M2_Lerntag_(\d{1,3})_(.+)$", re.IGNORECASE)
_LERNTAG_NUM_ONLY_RE = re.compile(r"^M2_Lerntag_(\d{1,3})$", re.IGNORECASE)
_LEADING_ORDER_RE = re.compile(r"^(\d{1,3})[_-](.+)$")
_LEADING_ZEROS_RE = re.compile(r"\b0+(\d)")
_NATURAL_SPLIT_RE = re.compile(r"(\d+)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CLOZE_RE = re.compile(r"\{\{c\d+::(.*?)(?:::(.*?))?\}\}", re.DOTALL)


def _norm_search_text(text: str) -> str:
    return _LEADING_ZEROS_RE.sub(r"\1", text.lower().strip())


def _natural_sort_key(text: str) -> list:
    return [int(tok) if tok.isdigit() else tok.lower() for tok in _NATURAL_SPLIT_RE.split(text)]


def format_topic_label(segment: str) -> str:
    """Turn a raw Ankizin tag segment into a clean human-readable German label."""
    s = segment.strip().lstrip("#!")
    if m := _LERNTAG_RE.match(s):
        num, topic = m.group(1).zfill(3), m.group(2).replace("_", " ").strip()
        return f"Tag {num} – {topic}"
    if m := _LERNTAG_NUM_ONLY_RE.match(s):
        return f"Tag {m.group(1).zfill(3)}"
    if m := _LEADING_ORDER_RE.match(s):
        # Strip numeric sort prefixes like "01_Innere_Medizin" unless it's a numbered step like "01-stark..."
        if not s.lower().startswith(("01-", "02-", "03-", "04-")):
            s = m.group(2)
    s = s.replace("_", " ").strip()
    s = re.sub(r"\s{2,}", " ", s)
    return s or segment


def _esc_tag(text: str) -> str:
    """Escape a tag string for literal Anki `tag:...` search."""
    return (
        text.replace("\\", "\\\\")
        .replace('"', r"\"")
        .replace("*", r"\*")
        .replace("_", r"\_")
    )


def _classify_note(tags: list[str]) -> tuple[int, int, list[tuple[str, list[str], str]]]:
    """Return (yield_bit, flags_mask, [(category_key, display_segments, full_tag), ...])."""
    yield_bit = 0
    flags_mask = 0
    topic_entries: list[tuple[str, list[str], str]] = []

    for tag in tags:
        m = _ROOT_RE.match(tag)
        if not m:
            continue
        rest = m.group(1)
        parts = [p for p in rest.split("::") if p]
        if not parts:
            continue

        p0 = parts[0].lower()

        # Internal / metadata branches
        if p0.startswith("!delete") or p0.startswith("§new_cards"):
            continue
        if p0 == "!markiere_diese_karten":
            joined = "::".join(parts[1:]).lower()
            if "01-" in joined or "stark_gelb" in joined:
                yield_bit |= YIELD_STARK
            elif "02-" in joined or "leicht_gelb" in joined:
                yield_bit |= YIELD_LEICHT
            elif "03-" in joined or "kein_gelb" in joined:
                yield_bit |= YIELD_STANDARD
            elif "04-" in joined or "low_yield" in joined or "verzichtbar" in joined:
                yield_bit |= YIELD_LOW
            if "!merke" in joined:
                flags_mask |= FLAG_MERKE
            if "ärztliches_wissen" in joined or "aerztliches_wissen" in joined:
                flags_mask |= FLAG_AERZTLICH
            if "top100" in joined or "top-100" in joined:
                flags_mask |= FLAG_TOP100
            continue
        if p0.startswith("zahni"):
            flags_mask |= FLAG_ZAHNI
            continue

        # Categorize content tags
        cat_key = "other"
        subparts = parts

        if p0.startswith("#m2_m3_klinik") or p0.startswith("m2_m3_klinik"):
            if len(parts) >= 2:
                p1 = parts[1].lower()
                if p1 in ("#amboss", "amboss"):
                    if len(parts) >= 3:
                        p2 = parts[2].lower()
                        if "bibliothek" in p2:
                            cat_key = "amboss"
                            subparts = parts[3:]
                        elif "100-tage-lernplan" in p2 or "lerntag" in p2:
                            cat_key = "lernplan"
                            subparts = parts[3:]
                        elif "top100" in p2 or "top-100" in p2:
                            cat_key = "top100"
                            flags_mask |= FLAG_TOP100
                            subparts = parts[3:]
                        elif p2.startswith("m3"):
                            cat_key = "m3"
                            subparts = parts[3:] if len(parts) > 3 else parts[2:]
                        else:
                            cat_key = "amboss"
                            subparts = parts[2:]
                    else:
                        cat_key = "amboss"
                        subparts = []
                elif "arzneistoff" in p1 or "pharma" in p1:
                    cat_key = "pharma"
                    subparts = parts[2:]
                else:
                    cat_key = "other"
                    subparts = parts[1:]
        elif p0.startswith("#m1_vorklinik") or p0.startswith("m1_vorklinik"):
            cat_key = "vorklinik"
            subparts = parts[1:]
        elif p0.startswith("#meditricks") or p0 == "meditricks":
            cat_key = "meditricks"
            subparts = parts[1:]
        elif p0.startswith("#universit") or p0.startswith("universit"):
            cat_key = "unis"
            subparts = parts[1:]

        if not subparts or cat_key not in _ALLOWED_CATEGORIES:
            continue
        topic_entries.append((cat_key, subparts, tag))

    # Notes with multiple yield tags take highest-priority bit; notes with none default to Standard.
    if yield_bit & YIELD_STARK:
        primary_yield = YIELD_STARK
    elif yield_bit & YIELD_LEICHT:
        primary_yield = YIELD_LEICHT
    elif yield_bit & YIELD_LOW:
        primary_yield = YIELD_LOW
    else:
        primary_yield = YIELD_STANDARD

    return primary_yield, flags_mask, topic_entries


@dataclass(frozen=True)
class TopicStats:
    total: int = 0
    active: int = 0
    suspended: int = 0
    stark: int = 0
    leicht: int = 0
    standard: int = 0
    low: int = 0


@dataclass
class TopicNode:
    key: str
    full_tag: str
    raw_segment: str
    display_name: str
    breadcrumb: str
    category_key: str
    all_tags: list[str] = field(default_factory=list)
    children: list["TopicNode"] = field(default_factory=list)
    # (yield_bit, flags_mask, is_suspended) -> unique card count
    buckets: dict[tuple[int, int, bool], int] = field(default_factory=dict)
    card_ids: frozenset[int] = field(default_factory=frozenset)

    def stats(
        self,
        yield_preset: str = "all",
        top100_only: bool = False,
        exclude_zahni: bool = True,
    ) -> TopicStats:
        mask = YIELD_PRESETS.get(yield_preset, YIELD_ALL)
        total = active = suspended = stark = leicht = standard = low = 0
        for (ybit, fmask, is_susp), cnt in self.buckets.items():
            if exclude_zahni and (fmask & FLAG_ZAHNI):
                continue
            if top100_only and not (fmask & FLAG_TOP100):
                continue
            if not (ybit & mask):
                continue
            total += cnt
            if is_susp:
                suspended += cnt
            else:
                active += cnt
            if ybit == YIELD_STARK:
                stark += cnt
            elif ybit == YIELD_LEICHT:
                leicht += cnt
            elif ybit == YIELD_STANDARD:
                standard += cnt
            elif ybit == YIELD_LOW:
                low += cnt
        return TopicStats(
            total=total,
            active=active,
            suspended=suspended,
            stark=stark,
            leicht=leicht,
            standard=standard,
            low=low,
        )


def _accumulate_bucket_into_presets(
    totals: dict[str, list[int]],
    ybit: int,
    fmask: int,
    is_susp: bool,
    cnt: int,
    top100_only: bool,
    exclude_zahni: bool,
) -> None:
    if exclude_zahni and (fmask & FLAG_ZAHNI):
        return
    if top100_only and not (fmask & FLAG_TOP100):
        return
    for key, mask in YIELD_PRESETS.items():
        if ybit & mask:
            arr = totals[key]
            arr[0] += cnt
            if is_susp:
                arr[2] += cnt
            else:
                arr[1] += cnt
            if ybit == YIELD_STARK:
                arr[3] += cnt
            elif ybit == YIELD_LEICHT:
                arr[4] += cnt
            elif ybit == YIELD_STANDARD:
                arr[5] += cnt
            elif ybit == YIELD_LOW:
                arr[6] += cnt


class AnkizinTagIndex:
    """Hierarchical topic index across all Ankizin categories."""

    def __init__(
        self,
        roots: dict[str, list[TopicNode]],
        all_nodes: list[TopicNode],
        collection_buckets: dict[tuple[int, int, bool], int],
        card_meta: Optional[dict[int, tuple[int, int, bool]]] = None,
    ) -> None:
        self.roots = roots
        self.all_nodes = all_nodes
        self.collection_buckets = collection_buckets
        self.card_meta = card_meta or {}

    def available_categories(self) -> list[tuple[str, str, str]]:
        return [cat for cat in CATEGORIES if self.roots.get(cat[0])]

    def combined_stats(
        self,
        nodes: list[TopicNode],
        yield_preset: str = "all",
        top100_only: bool = False,
        exclude_zahni: bool = True,
    ) -> TopicStats:
        """Exact deduplicated card stats across 1+ selected nodes in pure RAM (<1ms)."""
        if not nodes:
            return TopicStats()
        if len(nodes) == 1:
            return nodes[0].stats(yield_preset=yield_preset, top100_only=top100_only, exclude_zahni=exclude_zahni)

        mask = YIELD_PRESETS.get(yield_preset, YIELD_ALL)
        union_cids: set[int] = set()
        for n in nodes:
            union_cids.update(n.card_ids)

        total = active = suspended = stark = leicht = standard = low = 0
        meta_map = self.card_meta
        for cid in union_cids:
            meta = meta_map.get(cid)
            if meta is None:
                continue
            ybit, fmask, is_susp = meta
            if exclude_zahni and (fmask & FLAG_ZAHNI):
                continue
            if top100_only and not (fmask & FLAG_TOP100):
                continue
            if not (ybit & mask):
                continue
            total += 1
            if is_susp:
                suspended += 1
            else:
                active += 1
            if ybit == YIELD_STARK:
                stark += 1
            elif ybit == YIELD_LEICHT:
                leicht += 1
            elif ybit == YIELD_STANDARD:
                standard += 1
            elif ybit == YIELD_LOW:
                low += 1
        return TopicStats(
            total=total,
            active=active,
            suspended=suspended,
            stark=stark,
            leicht=leicht,
            standard=standard,
            low=low,
        )

    def yield_breakdown(
        self,
        nodes: list[TopicNode],
        top100_only: bool = False,
        exclude_zahni: bool = True,
    ) -> dict[str, TopicStats]:
        """Compute TopicStats for every yield preset in one fast RAM pass."""
        totals = {k: [0, 0, 0, 0, 0, 0, 0] for k in YIELD_PRESETS}
        if not nodes:
            return {k: TopicStats() for k in YIELD_PRESETS}

        if len(nodes) == 1:
            for (ybit, fmask, is_susp), cnt in nodes[0].buckets.items():
                _accumulate_bucket_into_presets(totals, ybit, fmask, is_susp, cnt, top100_only, exclude_zahni)
        else:
            union_cids: set[int] = set()
            for n in nodes:
                union_cids.update(n.card_ids)
            meta_map = self.card_meta
            for cid in union_cids:
                meta = meta_map.get(cid)
                if meta is not None:
                    _accumulate_bucket_into_presets(
                        totals, meta[0], meta[1], meta[2], 1, top100_only, exclude_zahni
                    )
        return {k: TopicStats(*v) for k, v in totals.items()}

    def collection_stats(
        self,
        yield_preset: str = "all",
        top100_only: bool = False,
        exclude_zahni: bool = True,
    ) -> TopicStats:
        dummy = TopicNode(
            key="root",
            full_tag="",
            raw_segment="",
            display_name="Ankizin",
            breadcrumb="",
            category_key="all",
            buckets=self.collection_buckets,
        )
        return dummy.stats(yield_preset=yield_preset, top100_only=top100_only, exclude_zahni=exclude_zahni)

    def search_tree(
        self,
        query: str,
        category_key: Optional[str] = None,
        yield_preset: str = "all",
        top100_only: bool = False,
        exclude_zahni: bool = True,
        limit: int = 60,
    ) -> list[TopicNode]:
        """Hierarchical top-down search: stops descending once all query tokens match
        so rare multi-subtopic articles (e.g. Pneumonie -> Diagnostik/Therapie) stay nested
        instead of flooding results with duplicate flat rows."""
        tokens = [_norm_search_text(t) for t in query.strip().split() if t.strip()]
        if not tokens:
            return []
        token_set = set(tokens)
        norm_query = " ".join(tokens)

        if category_key:
            root_lists = [self.roots.get(category_key, [])]
        else:
            root_lists = [self.roots.get(cat, []) for cat, _, _ in CATEGORIES]

        collected: list[tuple[TopicNode, int]] = []

        def _walk(node: TopicNode, ancestor_tokens: set[str]) -> None:
            st = node.stats(yield_preset=yield_preset, top100_only=top100_only, exclude_zahni=exclude_zahni)
            if st.total == 0:
                return
            name_norm = _norm_search_text(node.display_name)
            here_tokens = {t for t in token_set if t in name_norm}
            cum_tokens = ancestor_tokens | here_tokens
            if cum_tokens >= token_set:
                collected.append((node, st.total))
                return
            for ch in node.children:
                _walk(ch, cum_tokens)

        for rlist in root_lists:
            for root in rlist:
                _walk(root, set())

        def _rank_key(item: tuple[TopicNode, int]) -> tuple:
            node, total = item
            name_norm = _norm_search_text(node.display_name)
            if name_norm == norm_query:
                tier = 0
            elif name_norm.startswith(norm_query):
                tier = 1
            elif all(t in name_norm for t in token_set):
                tier = 2
            else:
                tier = 3
            return (tier, node.breadcrumb.count("›"), -total, _natural_sort_key(node.raw_segment))

        collected.sort(key=_rank_key)
        return [node for node, _ in collected[:limit]]

    def search(
        self,
        query: str,
        category_key: Optional[str] = None,
        yield_preset: str = "all",
        top100_only: bool = False,
        exclude_zahni: bool = True,
        limit: int = 80,
    ) -> list[TopicNode]:
        return self.search_tree(
            query=query,
            category_key=category_key,
            yield_preset=yield_preset,
            top100_only=top100_only,
            exclude_zahni=exclude_zahni,
            limit=limit,
        )


def build_tag_index(col: Optional[Collection]) -> AnkizinTagIndex:
    """Build a complete Ankizin topic tree in ONE SQL query with zero double counting."""
    if col is None:
        return AnkizinTagIndex({}, [], {})

    rows = col.db.all(
        "SELECT c.id, c.queue, n.id, n.tags "
        "FROM cards c JOIN notes n ON n.id = c.nid "
        "WHERE n.tags LIKE '%#Ankizin%' OR n.tags LIKE '%#Zankiphil%'"
    )

    # Cache unique tag path resolution -> ancestor nkeys tuple, and nid -> (ybit, fmask, unique_nkeys)
    tag_nkeys_cache: dict[tuple[str, str], tuple[tuple[str, tuple[str, ...]], ...]] = {}
    note_resolved_cache: dict[int, tuple[int, int, tuple[tuple[str, tuple[str, ...]], ...]]] = {}
    # node_key -> TopicNode (without finalized buckets yet)
    nodes_by_key: dict[tuple[str, tuple[str, ...]], TopicNode] = {}
    node_card_info: dict[tuple[str, tuple[str, ...]], dict[int, tuple[int, int, bool]]] = defaultdict(dict)
    collection_cards: dict[int, tuple[int, int, bool]] = {}
    root_keys: dict[str, set[tuple[str, ...]]] = defaultdict(set)

    for cid, queue, nid, raw_tags in rows:
        resolved = note_resolved_cache.get(nid)
        if resolved is None:
            tags = [t for t in (raw_tags or "").split() if t]
            # Skip notes marked for deletion so users never accidentally activate outdated cards
            if any("::!delete" in t.lower() for t in tags):
                note_resolved_cache[nid] = (0, 0, ())
                continue
            ybit, fmask, entries = _classify_note(tags)
            if not entries and ybit == 0:
                note_resolved_cache[nid] = (0, 0, ())
                continue

            seen_nkeys: dict[tuple[str, tuple[str, ...]], None] = {}
            for cat_key, subparts, full_tag in entries:
                tkey = (cat_key, full_tag)
                tag_nkeys = tag_nkeys_cache.get(tkey)
                if tag_nkeys is None:
                    m = _ROOT_RE.match(full_tag)
                    if not m:
                        tag_nkeys = ()
                    else:
                        all_parts = [p for p in m.group(1).split("::") if p]
                        root_prefix = full_tag[: len(full_tag) - len(m.group(1))]
                        prefix_len = len(all_parts) - len(subparts)
                        built_nkeys: list[tuple[str, tuple[str, ...]]] = []
                        for depth in range(1, len(subparts) + 1):
                            path_tuple = tuple(subparts[:depth])
                            norm_tuple = tuple(p.lower() for p in path_tuple)
                            nkey = (cat_key, norm_tuple)
                            raw_seg = subparts[depth - 1]
                            tag_parts = all_parts[: prefix_len + depth]
                            node_full_tag = root_prefix + "::".join(tag_parts)
                            if nkey not in nodes_by_key:
                                labels = [format_topic_label(p) for p in path_tuple]
                                node = TopicNode(
                                    key=f"{cat_key}::{'::'.join(norm_tuple)}",
                                    full_tag=node_full_tag,
                                    raw_segment=raw_seg,
                                    display_name=labels[-1],
                                    breadcrumb=" › ".join(labels),
                                    category_key=cat_key,
                                    all_tags=[node_full_tag],
                                )
                                nodes_by_key[nkey] = node
                                if depth == 1:
                                    root_keys[cat_key].add(norm_tuple)
                                else:
                                    parent_node = nodes_by_key[(cat_key, norm_tuple[:-1])]
                                    parent_node.children.append(node)
                            else:
                                existing = nodes_by_key[nkey]
                                if node_full_tag not in existing.all_tags:
                                    existing.all_tags.append(node_full_tag)
                                    if "#ankizin_vankicollab" in node_full_tag.lower():
                                        existing.full_tag = node_full_tag
                            built_nkeys.append(nkey)
                        tag_nkeys = tuple(built_nkeys)
                    tag_nkeys_cache[tkey] = tag_nkeys

                for nk in tag_nkeys:
                    seen_nkeys[nk] = None

            resolved = (ybit, fmask, tuple(seen_nkeys.keys()))
            note_resolved_cache[nid] = resolved

        ybit, fmask, unique_nkeys = resolved
        if not unique_nkeys and ybit == 0:
            continue

        card_meta = (ybit, fmask, queue == -1)
        collection_cards[cid] = card_meta
        for nkey in unique_nkeys:
            node_card_info[nkey][cid] = card_meta

    # Finalize bucket counters and immutable card id sets
    all_nodes: list[TopicNode] = []
    for nkey, node in nodes_by_key.items():
        buckets: dict[tuple[int, int, bool], int] = defaultdict(int)
        cids_map = node_card_info[nkey]
        for meta in cids_map.values():
            buckets[meta] += 1
        node.buckets = dict(buckets)
        node.card_ids = frozenset(cids_map.keys())
        node.children.sort(key=lambda ch: _natural_sort_key(ch.raw_segment))
        all_nodes.append(node)

    roots: dict[str, list[TopicNode]] = {}
    for cat_key, key_set in root_keys.items():
        cat_roots = [nodes_by_key[(cat_key, pt)] for pt in key_set]
        cat_roots.sort(key=lambda ch: _natural_sort_key(ch.raw_segment))
        roots[cat_key] = cat_roots

    col_buckets: dict[tuple[int, int, bool], int] = defaultdict(int)
    for meta in collection_cards.values():
        col_buckets[meta] += 1

    return AnkizinTagIndex(
        roots=roots,
        all_nodes=all_nodes,
        collection_buckets=dict(col_buckets),
        card_meta=collection_cards,
    )


# ── Search Query Builder ─────────────────────────────────────────────────────

_STARK_PATTERNS = (
    "#Ankizin_*::" + _esc_tag("!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-") + "*",
    "#Ankizin_*::" + _esc_tag("!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)::stark_gelb_M2"),
    "#Ankizin_*::" + _esc_tag("!MARKIERE_DIESE_KARTEN::M1_IMPP-Relevanz_(yield)::01-") + "*",
)
_LEICHT_PATTERNS = (
    "#Ankizin_*::" + _esc_tag("!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::02-") + "*",
    "#Ankizin_*::" + _esc_tag("!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)::leicht_gelb_M2"),
    "#Ankizin_*::" + _esc_tag("!MARKIERE_DIESE_KARTEN::M1_IMPP-Relevanz_(yield)::02-") + "*",
)
_LOW_PATTERNS = (
    "#Ankizin_*::" + _esc_tag("!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::04-") + "*",
    "#Ankizin_*::" + _esc_tag("!MARKIERE_DIESE_KARTEN::M2_high_yield_(IMPP-Relevanz)::M2_low_yield"),
    "#Ankizin_*::" + _esc_tag("!MARKIERE_DIESE_KARTEN::M1_IMPP-Relevanz_(yield)::04-") + "*",
)


def _or_tags(patterns: tuple[str, ...]) -> str:
    return "(" + " OR ".join(f'"tag:{p}"' for p in patterns) + ")"


def build_topic_search(
    tags: list[str],
    yield_preset: str = "high_yield",
    top100_only: bool = False,
    exclude_zahni: bool = True,
    exclude_delete: bool = True,
) -> str:
    """Build an exact, properly escaped Anki search string for selected topic tags + filters."""
    clean_tags = [t for t in tags if t]
    if not clean_tags:
        return ""

    if len(clean_tags) == 1:
        topic_clause = f'"tag:{_esc_tag(clean_tags[0])}"'
    else:
        topic_clause = "(" + " OR ".join(f'"tag:{_esc_tag(t)}"' for t in clean_tags) + ")"

    parts = [topic_clause]

    if exclude_delete:
        parts.append('-"tag:#Ankizin_*::!DELETE"')

    if exclude_zahni:
        parts.append('-"tag:#Ankizin_*::Zahni-Fokus"')

    if top100_only:
        t1 = "#Ankizin_*::" + _esc_tag("#M2_M3_Klinik::#AMBOSS::M2-TOP100-Themen")
        t2 = "#Ankizin_*::" + _esc_tag("#M2_M3_Klinik::#AMBOSS::M2-TOP-100-Themen")
        parts.append(f'("tag:{t1}" OR "tag:{t2}")')

    if yield_preset == "stark":
        parts.append(_or_tags(_STARK_PATTERNS))
    elif yield_preset == "high_yield":
        parts.append(_or_tags(_STARK_PATTERNS + _LEICHT_PATTERNS))
    elif yield_preset == "standard":
        parts.append("-" + _or_tags(_LOW_PATTERNS))

    return " ".join(parts)


# ── Card Preview ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CardPreview:
    cid: int
    nid: int
    snippet: str
    yield_level: str  # "stark" | "leicht" | "standard" | "low"
    status: str  # "pausiert" | "neu" | "fällig" | "gelernt"


def _prettify_card_text(raw_html: str, max_len: int = 165) -> str:
    text = _CLOZE_RE.sub(lambda m: f"[{m.group(1)}]", raw_html or "")
    text = _HTML_TAG_RE.sub(" ", text)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text or "(Ohne Textvorschau – z. B. Bildkarte)"


def fetch_topic_preview(
    col: Optional[Collection],
    tags: list[str],
    yield_preset: str = "high_yield",
    top100_only: bool = False,
    exclude_zahni: bool = True,
    limit: int = 10,
) -> list[CardPreview]:
    """Fetch clean text previews & status badges for cards matching the selection."""
    if col is None or not tags:
        return []
    query = build_topic_search(
        tags,
        yield_preset=yield_preset,
        top100_only=top100_only,
        exclude_zahni=exclude_zahni,
    )
    if not query:
        return []

    cids = col.find_cards(query)[:limit]
    previews: list[CardPreview] = []
    for cid in cids:
        card = col.get_card(cid)
        note = card.note()
        # Pick the primary prompt field (Text / Frage / first non-empty field)
        raw_field = ""
        for idx, fld_name in enumerate(note.keys()):
            if fld_name.lower() in ("text", "frage", "front", "vorderseite") and note.fields[idx].strip():
                raw_field = note.fields[idx]
                break
        if not raw_field:
            raw_field = next((f for f in note.fields if f and f.strip()), "")

        ybit, _, _ = _classify_note(note.tags)
        yield_name = {
            YIELD_STARK: "stark",
            YIELD_LEICHT: "leicht",
            YIELD_STANDARD: "standard",
            YIELD_LOW: "low",
        }.get(ybit, "standard")

        if card.queue == -1:
            status = "pausiert"
        elif card.type == 0:
            status = "neu"
        elif card.queue in (1, 2, 3):
            status = "fällig"
        else:
            status = "gelernt"

        previews.append(
            CardPreview(
                cid=cid,
                nid=note.id,
                snippet=_prettify_card_text(raw_field),
                yield_level=yield_name,
                status=status,
            )
        )
    return previews
