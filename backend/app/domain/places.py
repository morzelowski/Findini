"""Lokalny katalog miejscowości Polski (GeoNames, CC BY 4.0).

Zapytania i współrzędne nie są wysyłane do zewnętrznego geokodera.
Zwracany punkt to środek miejscowości; miejsce zdarzenia wybiera użytkownik.
"""

from __future__ import annotations

import csv
import gzip
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.matching import norm
from app.geo import haversine_m


@lru_cache(maxsize=1)
def catalog() -> tuple[dict[str, Any], ...]:
    path = Path(__file__).resolve().parents[1] / "data" / "places_pl.tsv.gz"
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return tuple(
            {
                "key": f"gn:{gid}",
                "name": name,
                "lat": float(lat),
                "lon": float(lon),
                "region": region,
                "county": county,
                "population": int(pop),
                "normalized": norm(name),
                "searchable": norm(name + " " + region + " " + county),
            }
            for gid, name, lat, lon, region, county, pop in csv.reader(f, delimiter="\t")
        )


def public_place(p: dict[str, Any]) -> dict[str, Any]:
    return {k: p[k] for k in ("key", "name", "lat", "lon", "region", "county")}


def popular_places() -> list[dict[str, Any]]:
    capitals = {
        "Warszawa",
        "Kraków",
        "Łódź",
        "Wrocław",
        "Poznań",
        "Gdańsk",
        "Szczecin",
        "Bydgoszcz",
        "Lublin",
        "Białystok",
        "Katowice",
        "Kielce",
        "Rzeszów",
        "Olsztyn",
        "Opole",
        "Toruń",
        "Zielona Góra",
        "Gorzów Wielkopolski",
    }
    cities = sorted((p for p in catalog() if p["name"] in capitals), key=lambda p: -p["population"])
    seen: set[str] = set()
    result = []
    for p in cities:
        if p["name"] not in seen:
            result.append(public_place(p))
            seen.add(p["name"])
    return result


@lru_cache(maxsize=256)
def search_places(query: str) -> tuple[dict[str, Any], ...]:
    q = norm(query).strip()
    if len(q) < 2:
        return ()
    words = q.split()
    candidates = []
    for p in catalog():
        name = p["normalized"]
        full = p["searchable"]
        if not all(w in full for w in words):
            continue
        rank = 0 if name == q else 1 if name.startswith(q) else 2 if words[0] in name else 3
        candidates.append((rank, -p["population"], name, p["key"], p))
    candidates.sort(key=lambda row: row[:4])
    return tuple(public_place(p) for *_, p in candidates[:20])


def nearest_place(lat: float, lon: float) -> dict[str, Any] | None:
    # Prosty filtr prostokątny ogranicza koszt do kilkunastu miejscowości.
    nearby = (p for p in catalog() if abs(p["lat"] - lat) < 0.045 and abs(p["lon"] - lon) < 0.07)
    best = min(nearby, key=lambda p: haversine_m(lat, lon, p["lat"], p["lon"]), default=None)
    if best is None or haversine_m(lat, lon, best["lat"], best["lon"]) > 4000:
        return None
    return public_place(best)


_FORMS = {
    "warszawa": ["warszawie", "warszawy"],
    "krakow": ["krakowie", "krakowa"],
    "lodz": ["lodzi"],
    "wroclaw": ["wroclawiu", "wroclawia"],
    "poznan": ["poznaniu", "poznania"],
    "gdansk": ["gdansku", "gdanska"],
    "szczecin": ["szczecinie", "szczecina"],
    "bydgoszcz": ["bydgoszczy"],
    "lublin": ["lublinie", "lublina"],
    "bialystok": ["bialymstoku", "bialegostoku"],
    "katowice": ["katowicach", "katowic"],
    "gdynia": ["gdyni"],
    "czestochowa": ["czestochowie", "czestochowy"],
    "radom": ["radomiu", "radomia"],
    "torun": ["toruniu", "torunia"],
    "rzeszow": ["rzeszowie", "rzeszowa"],
    "olsztyn": ["olsztynie", "olsztyna"],
    "kielce": ["kielcach", "kielc"],
    "opole": ["opolu", "opola"],
    "zielona gora": ["zielonej gorze", "zielonej gory"],
    "gorzow wielkopolski": ["gorzowie wielkopolskim"],
    "sopot": ["sopocie", "sopotu"],
    "biala podlaska": ["bialej podlaskiej"],
    "bielsko-biala": ["bielsku-bialej"],
}


def city_in_text(text: str) -> tuple[dict[str, Any], list[str]] | None:
    # Tylko jednoznaczne, większe miasta. Mniejsze miejscowości użytkownik wybiera
    # w wyszukiwarce; nie zgadujemy, o którą z wielu wsi o tej samej nazwie chodzi.
    cities = sorted((p for p in catalog() if p["population"] >= 20000), key=lambda p: -len(p["normalized"]))
    for p in cities:
        forms = [p["normalized"], *_FORMS.get(p["normalized"], [])]
        if any(re.search(r"(?<![a-z])" + re.escape(f) + r"(?![a-z])", text) for f in forms):
            matches = [c for c in cities if c["normalized"] == p["normalized"]]
            if len(matches) == 1:
                return public_place(p), forms
    return None
