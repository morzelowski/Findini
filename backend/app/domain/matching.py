"""Wyjaśnialny ranking wyników i dopasowań zgubione <-> znalezione.

Każdy sygnał daje punkty i krótkie uzasadnienie po polsku. Niezgodności (inny kolor,
inna marka, znalezione przed zgubieniem) są pokazywane jako ostrzeżenia i obniżają
poziom dopasowania — wysokie podobieństwo zdjęcia ich nie ukrywa.

Wynik punktowy służy tylko do sortowania; użytkownik widzi poziom („mocne”, „możliwe”)
oraz sygnały, nigdy „procent pewności”.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.domain.categories import CATEGORY_BY_KEY, COLOR_PL, attr_label, strong_attr_keys
from app.geo import haversine_m, rounded_distance_m

# Progi wyznaczone w eksperymencie (docs/EKSPERYMENT_AI.md, CLIP ViT-B/32 fp32):
# - bezwzględne podobieństwo słabo odróżnia egzemplarze tego samego typu (mediana par
#   pozytywnych 0,81 vs. najtrudniejszy negatyw tego samego typu 0,83) — używamy go tylko jako
#   słabego sygnału i do odróżnienia innych kategorii;
# - „wyróżniające się” podobieństwo: przewaga najlepszego wyniku nad drugim >= 0,05
#   (precyzja ok. 0,7 na zbiorze testowym) — dopiero to opisujemy mocniej.
SIM_SIMILAR = 0.86
SIM_RELATED = 0.80
DISTINCT_MARGIN = 0.05

# Kolory, które ludzie często opisują zamiennie (częściowa zgodność).
_NEAR_COLORS = {
    frozenset({"navy", "blue"}),
    frozenset({"navy", "black"}),
    frozenset({"gray", "silver"}),
    frozenset({"beige", "brown"}),
    frozenset({"gold", "yellow"}),
    frozenset({"white", "beige"}),
    frozenset({"pink", "red"}),
    frozenset({"purple", "pink"}),
    frozenset({"orange", "red"}),
    frozenset({"gray", "black"}),
    frozenset({"white", "silver"}),
}


@dataclass
class QueryCtx:
    category: str | None = None
    colors: list[str] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)
    text: str | None = None
    lat: float | None = None
    lon: float | None = None
    radius_m: int | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None
    # Gdy dopasowujemy do konkretnego zgłoszenia: jego rodzaj (lost/found)
    source_kind: str | None = None
    category_is_filter: bool = False


@dataclass
class Cand:
    id: Any
    kind: str
    category: str
    colors: list[str]
    attrs: dict[str, Any]
    lat: float
    lon: float
    occurred_from: datetime
    occurred_to: datetime
    text_sim: float | None = None
    image_sim: float | None = None
    image_distinct: bool = False


@dataclass
class Explained:
    score: float
    tier: str  # strong | possible | weak
    reasons: list[str]
    warnings: list[str]
    distance_m: int | None


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.replace("ł", "l").strip()


def _fmt_dist(m: int) -> str:
    if m < 1000:
        return f"ok. {max(m, 100)} m"
    return "ok. " + f"{m / 1000:.1f}".replace(".", ",") + " km"


def _fmt_gap(td: timedelta) -> str:
    h = td.total_seconds() / 3600
    if h < 1:
        return "w ciągu godziny"
    if h < 24:
        return f"ok. {int(round(h))} h"
    d = int(round(h / 24))
    return f"ok. {d} {'dzień' if d == 1 else 'dni'}"


def color_relation(a: list[str], b: list[str]) -> str:
    """'match' | 'near' | 'conflict' | 'unknown' (pomijamy 'wielokolorowy')."""
    a2 = [c for c in a if c != "multi"]
    b2 = [c for c in b if c != "multi"]
    if not a2 or not b2:
        return "unknown"
    if set(a2) & set(b2):
        return "match"
    for x in a2:
        for y in b2:
            if frozenset({x, y}) in _NEAR_COLORS:
                return "near"
    return "conflict"


def explain(q: QueryCtx, c: Cand) -> Explained:
    score = 0.0
    reasons: list[str] = []
    warnings: list[str] = []
    serious = False
    # „Mocne” wymaga choć jednej cechy wyróżniającej egzemplarz, nie tylko kategorii/miejsca/czasu.
    distinguishing = False

    # Kategoria
    if q.category:
        if c.category == q.category:
            if not q.category_is_filter:
                score += 3
                reasons.append(f"Ta sama kategoria: {CATEGORY_BY_KEY[c.category].label.lower()}")
            else:
                score += 1
        else:
            score -= 3
            warnings.append("Inna kategoria")
            serious = True

    # Kolory
    rel = color_relation(q.colors, c.colors)
    if rel == "match":
        common = [COLOR_PL[x] for x in c.colors if x in q.colors and x != "multi"]
        score += 2
        distinguishing = True
        reasons.append(f"Kolor: {', '.join(common)}")
    elif rel == "near":
        score += 0.75
        reasons.append("Zbliżony kolor")
    elif rel == "conflict":
        score -= 2
        theirs = ", ".join(COLOR_PL[x] for x in c.colors)
        ours = ", ".join(COLOR_PL[x] for x in q.colors)
        warnings.append(f"Inny kolor ({theirs} zamiast {ours})")
        serious = True

    # Cechy charakterystyczne (marka, rodzaj, brelok…)
    cat = c.category
    for key in strong_attr_keys(cat):
        qv, cv = q.attrs.get(key), c.attrs.get(key)
        if qv in (None, "") or cv in (None, ""):
            continue
        label = attr_label(cat, key)
        if norm(str(qv)) == norm(str(cv)) or (
            len(norm(str(qv))) >= 3 and (norm(str(qv)) in norm(str(cv)) or norm(str(cv)) in norm(str(qv)))
        ):
            score += 2
            distinguishing = distinguishing or key != "subtype"
            reasons.append(f"{label}: {cv}")
        else:
            score -= 1.5 if key == "subtype" else 2
            warnings.append(f"Inna cecha — {label.lower()}: {cv}")
            if key != "subtype":
                serious = True

    # Odległość (tylko publiczne środki komórek)
    dist: int | None = None
    if q.lat is not None and q.lon is not None:
        raw = haversine_m(q.lat, q.lon, c.lat, c.lon)
        dist = rounded_distance_m(raw)
        if q.radius_m is not None and raw <= q.radius_m:
            reasons.append(f"W wybranym obszarze ({_fmt_dist(dist)})")
            score += 1.5 if raw <= 1000 else 1
        elif raw <= 1000:
            score += 2
            reasons.append(f"Blisko ({_fmt_dist(dist)})")
        elif raw <= 3000:
            score += 1
            reasons.append(f"W pobliżu ({_fmt_dist(dist)})")
        elif raw > 8000:
            score -= 1
            warnings.append(f"Daleko ({_fmt_dist(dist)})")

    # Czas
    if q.source_kind is not None and q.time_from is not None and q.time_to is not None:
        if q.source_kind == "lost" and c.kind == "found":
            lost_from, lost_to, found_from, found_to = q.time_from, q.time_to, c.occurred_from, c.occurred_to
        else:
            lost_from, lost_to, found_from, found_to = c.occurred_from, c.occurred_to, q.time_from, q.time_to
        if found_to < lost_from - timedelta(hours=6):
            score -= 3
            warnings.append("Znalezione wcześniej, niż zgłoszono zgubienie")
            serious = True
        else:
            gap = max(timedelta(0), found_from - lost_to)
            if gap <= timedelta(days=2):
                score += 1.5
                reasons.append(f"Zgodny czas (odstęp {_fmt_gap(gap)})")
            elif gap <= timedelta(days=14):
                score += 0.5
                reasons.append(f"Znalezione {_fmt_gap(gap)} później")
    elif q.time_from is not None or q.time_to is not None:
        tf = q.time_from or datetime.min.replace(tzinfo=c.occurred_from.tzinfo)
        tt = q.time_to or datetime.max.replace(tzinfo=c.occurred_to.tzinfo)
        if c.occurred_to >= tf and c.occurred_from <= tt:
            score += 1
            reasons.append("W wybranym czasie")

    # Tekst
    if c.text_sim is not None and q.text:
        if c.text_sim >= 0.6:
            score += 2
            reasons.append(f"Opis pasuje do „{q.text[:30]}”")
        elif c.text_sim >= 0.35:
            score += 1
            reasons.append(f"Opis częściowo pasuje do „{q.text[:30]}”")

    # Zdjęcie (sygnał pomocniczy — nigdy dowód)
    if c.image_sim is not None:
        if c.image_distinct and c.image_sim >= SIM_RELATED:
            score += 2.5
            distinguishing = True
            reasons.append("Zdjęcie wyróżnia się podobieństwem spośród kandydatów")
        elif c.image_sim >= SIM_SIMILAR:
            score += 1
            reasons.append("Zdjęcie podobne wizualnie")

    if score >= 6 and not serious and distinguishing:
        tier = "strong"
    elif score >= 3:
        tier = "possible"
    else:
        tier = "weak"
    return Explained(score=score, tier=tier, reasons=reasons, warnings=warnings, distance_m=dist)
