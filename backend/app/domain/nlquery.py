"""Asystent wyszukiwania: zamienia zdanie po polsku na edytowalne filtry.

Działa na regułach i słownikach (bez zewnętrznego LLM, bez kluczy, deterministycznie).
Tekst użytkownika jest tylko danymi — nie ma tu żadnych "instrukcji" do wykonania.
Wynik to propozycja; aplikacja pokazuje rozpoznane filtry do akceptacji/edycji.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.categories import CATEGORY_BY_KEY, COLOR_PL
from app.domain.matching import norm

TZ = ZoneInfo("Europe/Warsaw")

# rdzeń (bez polskich znaków) -> (kategoria, rodzaj)
_ITEMS: list[tuple[str, str, str | None]] = [
    ("czapk", "clothing", "czapka"),
    ("czapeczk", "clothing", "czapka"),
    ("beanie", "clothing", "czapka"),
    ("kaszkiet", "clothing", "czapka"),
    ("szalik", "clothing", "szalik"),
    ("chust", "clothing", "szalik"),
    ("rekawicz", "clothing", "rękawiczki"),
    ("kurtk", "clothing", "kurtka"),
    ("plaszcz", "clothing", "kurtka"),
    ("bluz", "clothing", "bluza / sweter"),
    ("swet", "clothing", "bluza / sweter"),
    ("plecak", "bags", "plecak"),
    ("torebk", "bags", "torebka"),
    ("torb", "bags", None),
    ("walizk", "bags", "walizka"),
    ("saszetk", "bags", "worek / saszetka"),
    ("nerk", "bags", "worek / saszetka"),
    ("portfel", "wallets", "portfel"),
    ("portmonetk", "wallets", "portfel"),
    ("etui na kart", "wallets", "etui na karty"),
    ("dowod", "wallets", "dowód osobisty"),
    ("legitymac", "wallets", "legitymacja"),
    ("prawo jazdy", "wallets", "prawo jazdy"),
    ("paszport", "wallets", "paszport"),
    ("karta platnicz", "wallets", "karta płatnicza"),
    ("karte platnicz", "wallets", "karta płatnicza"),
    ("kluczyk", "keys", "kluczyk samochodowy"),
    ("klucz", "keys", "pęk kluczy"),
    ("pek", "keys", "pęk kluczy"),
    ("telefon", "electronics", "telefon"),
    ("smartfon", "electronics", "telefon"),
    ("komork", "electronics", "telefon"),
    ("iphone", "electronics", "telefon"),
    ("laptop", "electronics", "laptop"),
    ("notebook", "electronics", "laptop"),
    ("macbook", "electronics", "laptop"),
    ("tablet", "electronics", "tablet"),
    ("ipad", "electronics", "tablet"),
    ("sluchawk", "electronics", "słuchawki"),
    ("airpods", "electronics", "słuchawki"),
    ("ladowark", "electronics", "ładowarka / powerbank"),
    ("powerbank", "electronics", "ładowarka / powerbank"),
    ("smartwatch", "electronics", "smartwatch"),
    ("aparat", "electronics", "aparat"),
    ("pendrive", "electronics", "pendrive / dysk"),
    ("zegarek", "jewelry", "zegarek"),
    ("pierscion", "jewelry", "pierścionek"),
    ("obraczk", "jewelry", "pierścionek"),
    ("naszyjnik", "jewelry", "naszyjnik"),
    ("lancuszek", "jewelry", "naszyjnik"),
    ("bransolet", "jewelry", "bransoletka"),
    ("kolczyk", "jewelry", "kolczyki"),
    ("okular", "accessories", "okulary"),
    ("parasol", "accessories", "parasol"),
    ("bidon", "accessories", "bidon / kubek"),
    ("kubek", "accessories", "bidon / kubek"),
    ("termos", "accessories", "bidon / kubek"),
    ("ksiazk", "accessories", "książka / zeszyt"),
    ("zeszyt", "accessories", "książka / zeszyt"),
    ("zabawk", "accessories", "zabawka"),
    ("maskotk", "accessories", "zabawka"),
    ("pluszak", "accessories", "zabawka"),
]

_COLORS: list[tuple[str, str]] = [
    ("czarn", "black"),
    ("bial", "white"),
    ("szar", "gray"),
    ("srebrn", "silver"),
    ("zlot", "gold"),
    ("brazow", "brown"),
    ("bezow", "beige"),
    ("czerwon", "red"),
    ("rozow", "pink"),
    ("pomaranczow", "orange"),
    ("zolt", "yellow"),
    ("zielon", "green"),
    ("niebiesk", "blue"),
    ("granatow", "navy"),
    ("fiolet", "purple"),
    ("kolorow", "multi"),
    ("wielokolor", "multi"),
]

_BRANDS = [
    "Apple",
    "Samsung",
    "Xiaomi",
    "Huawei",
    "Motorola",
    "OnePlus",
    "Google",
    "Sony",
    "JBL",
    "Bose",
    "Dell",
    "HP",
    "Lenovo",
    "Asus",
    "Acer",
    "MSI",
    "Garmin",
    "Casio",
    "Nike",
    "Adidas",
    "Puma",
    "Reebok",
    "New Balance",
    "The North Face",
    "Eastpak",
    "Herschel",
    "Fjallraven",
    "Kanken",
    "Jansport",
    "Vans",
    "Quechua",
    "4F",
    "Wittchen",
    "Ochnik",
    "Tommy Hilfiger",
    "Levi's",
    "Zara",
    "Reserved",
]

# Orientacyjne punkty w Krakowie (publiczne miejsca) — szybki wybór obszaru i etykiety „okolice: …”.
LANDMARKS: list[dict[str, Any]] = [
    {"key": "rynek", "name": "Rynek Główny", "lat": 50.0617, "lon": 19.9373, "aliases": ["rynek", "sukiennic"]},
    {
        "key": "dworzec",
        "name": "Dworzec Główny / Galeria Krakowska",
        "lat": 50.0675,
        "lon": 19.9450,
        "aliases": ["dworzec", "dworc", "galeri krakowsk", "galeria krakowska"],
    },
    {"key": "agh", "name": "Kampus AGH", "lat": 50.0656, "lon": 19.9189, "aliases": ["agh"]},
    {
        "key": "uj",
        "name": "Collegium Novum UJ",
        "lat": 50.0610,
        "lon": 19.9338,
        "aliases": ["collegium", "uniwersytet jagiellonski", " uj"],
    },
    {
        "key": "ruczaj",
        "name": "Kampus UJ (Ruczaj)",
        "lat": 50.0287,
        "lon": 19.9065,
        "aliases": ["ruczaj", "kampus uj", "kampusie uj", "lojasiewicza"],
    },
    {
        "key": "pk",
        "name": "Politechnika Krakowska (ul. Warszawska)",
        "lat": 50.0712,
        "lon": 19.9435,
        "aliases": ["politechnik", " pk "],
    },
    {
        "key": "uek",
        "name": "Uniwersytet Ekonomiczny",
        "lat": 50.0688,
        "lon": 19.9548,
        "aliases": ["ekonomiczn", "uek", "rakowick"],
    },
    {
        "key": "kazimierz",
        "name": "Kazimierz (Plac Nowy)",
        "lat": 50.0517,
        "lon": 19.9447,
        "aliases": ["kazimierz", "plac nowy", "placu nowym"],
    },
    {"key": "wawel", "name": "Wawel", "lat": 50.0540, "lon": 19.9354, "aliases": ["wawel"]},
    {"key": "blonia", "name": "Błonia", "lat": 50.0597, "lon": 19.9128, "aliases": ["blonia", "bloniach"]},
    {
        "key": "nowa_huta",
        "name": "Nowa Huta (Plac Centralny)",
        "lat": 50.0722,
        "lon": 20.0378,
        "aliases": ["nowa huta", "nowej hucie", "plac centralny", "placu centralnym"],
    },
    {"key": "bonarka", "name": "Bonarka", "lat": 50.0283, "lon": 19.9531, "aliases": ["bonark"]},
    {"key": "tauron", "name": "Tauron Arena", "lat": 50.0676, "lon": 19.9915, "aliases": ["tauron", "arena"]},
    {"key": "mogilskie", "name": "Rondo Mogilskie", "lat": 50.0655, "lon": 19.9600, "aliases": ["mogilski"]},
]

_WEEKDAYS = [
    ("poniedzial", 0),
    ("wtor", 1),
    ("srod", 2),
    ("czwart", 3),
    ("piat", 4),
    ("sobot", 5),
    ("niedziel", 6),
]


@dataclass
class Parsed:
    kind: str | None = None
    category: str | None = None
    subtype: str | None = None
    colors: list[str] = field(default_factory=list)
    brand: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    place: dict[str, Any] | None = None
    text: str | None = None
    understood: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "category": self.category,
            "subtype": self.subtype,
            "colors": self.colors,
            "brand": self.brand,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "place": self.place,
            "text": self.text,
            "understood": self.understood,
        }


def _day_range(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, TZ)
    end = datetime.combine(d, time.max, TZ)
    return start, end


def parse_query(raw: str, now: datetime | None = None) -> Parsed:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    text = " " + norm(raw[:300]) + " "
    p = Parsed()
    consumed: list[str] = []

    # Kogo szukamy: „zgubiłem” => szukam wśród znalezionych.
    if re.search(r"\b(zgubi\w*|zgubion\w*|stracil\w*|zostawil\w*|zapodzial\w*|ukradzion\w*)", text):
        p.kind = "found"
        p.understood.append("Szukasz wśród znalezionych rzeczy")
        consumed += re.findall(r"\b(zgubi\w*|zgubion\w*|stracil\w*|zostawil\w*|zapodzial\w*)", text)
    elif re.search(r"\b(znalazl\w*|znalezion\w*|znalezl\w*)", text):
        p.kind = "lost"
        p.understood.append("Szukasz wśród zgubionych rzeczy (właściciela)")
        consumed += re.findall(r"\b(znalazl\w*|znalezion\w*|znalezl\w*)", text)

    for stem, cat, sub in _ITEMS:
        m = re.search(r"(?<![a-z])" + re.escape(stem) + r"\w*", text)
        if m:
            p.category, p.subtype = cat, sub
            consumed.append(m.group(0))
            label = CATEGORY_BY_KEY[cat].label
            p.understood.append(f"Kategoria: {label}" + (f" ({sub})" if sub else ""))
            break

    for stem, key in _COLORS:
        for m in re.finditer(r"(?<![a-z])" + re.escape(stem) + r"\w*", text):
            if key not in p.colors and len(p.colors) < 3:
                p.colors.append(key)
            consumed.append(m.group(0))
    if p.colors:
        p.understood.append("Kolor: " + ", ".join(COLOR_PL[c] for c in p.colors))

    for b in _BRANDS:
        if re.search(r"(?<![a-z0-9])" + re.escape(norm(b)) + r"(?![a-z0-9])", text):
            p.brand = b
            consumed.append(norm(b))
            p.understood.append(f"Marka: {b}")
            break

    today = now.date()
    if re.search(r"\bprzedwczoraj\b", text):
        p.date_from, p.date_to = _day_range(today - timedelta(days=2))
        p.understood.append("Czas: przedwczoraj")
        consumed.append("przedwczoraj")
    elif re.search(r"\bwczoraj\b", text):
        p.date_from, p.date_to = _day_range(today - timedelta(days=1))
        p.understood.append("Czas: wczoraj")
        consumed.append("wczoraj")
    elif re.search(r"\b(dzis|dzisiaj|rano|wieczorem)\b", text):
        p.date_from, p.date_to = _day_range(today)
        p.understood.append("Czas: dzisiaj")
        consumed += re.findall(r"\b(dzis|dzisiaj)\b", text)
    elif m := re.search(r"\b(\d{1,2}) dni temu\b", text):
        n = min(int(m.group(1)), 60)
        p.date_from, p.date_to = _day_range(today - timedelta(days=n))
        p.date_from -= timedelta(days=1)
        p.date_to += timedelta(days=1)
        p.understood.append(f"Czas: ok. {n} dni temu (±1 dzień)")
        consumed.append(m.group(0))
    elif re.search(r"\b(w zeszlym tygodniu|tydzien temu|w tym tygodniu)\b", text):
        p.date_from = datetime.combine(today - timedelta(days=8), time.min, TZ)
        p.date_to = now
        p.understood.append("Czas: ostatni tydzień")
        consumed += ["tygodniu", "tydzien", "temu", "zeszlym"]
    elif re.search(r"\bweekend\w*", text):
        delta = (today.weekday() - 5) % 7
        sat = today - timedelta(days=delta)
        p.date_from, _ = _day_range(sat)
        _, p.date_to = _day_range(sat + timedelta(days=1))
        p.understood.append("Czas: ostatni weekend")
        consumed.append("weekend")
    else:
        for stem, wd in _WEEKDAYS:
            if re.search(r"\b(w |we )?" + stem + r"\w*", text):
                delta = (today.weekday() - wd) % 7 or 7
                p.date_from, p.date_to = _day_range(today - timedelta(days=delta))
                p.understood.append(f"Czas: ostatni dzień tygodnia ({stem}…)")
                consumed.append(stem)
                break

    for lm in LANDMARKS:
        if any(a in text for a in lm["aliases"]):
            p.place = {"key": lm["key"], "name": lm["name"], "lat": lm["lat"], "lon": lm["lon"], "radius_m": 1500}
            p.understood.append(f"Miejsce: okolice — {lm['name']} (1,5 km)")
            consumed += lm["aliases"]
            break

    stop = {
        "w",
        "we",
        "na",
        "przy",
        "kolo",
        "obok",
        "pod",
        "z",
        "ze",
        "i",
        "a",
        "o",
        "do",
        "u",
        "od",
        "moj",
        "moja",
        "moje",
        "mojego",
        "jest",
        "gdzies",
        "chyba",
        "sie",
        "ktos",
        "czy",
        "ten",
        "ta",
        "to",
        "zgubilem",
        "zgubilam",
        "zostal",
        "zostala",
        "temu",
        "okolo",
        "okolicy",
        "okolicach",
        "uczelni",
    }
    leftovers = []
    for w in re.findall(r"[a-z0-9]+", text):
        if w in stop or any(w.startswith(c.strip()) or c.strip().startswith(w) for c in consumed if c.strip()):
            continue
        if len(w) >= 3:
            leftovers.append(w)
    if leftovers:
        p.text = " ".join(leftovers[:6])
    if not p.understood:
        p.understood.append("Nie rozpoznano filtrów — wyszukam po tekście")
        p.text = " ".join(re.findall(r"[a-z0-9]+", text))[:80] or None
    return p


def nearest_landmark(lat: float, lon: float, max_m: float = 1500) -> dict[str, Any] | None:
    from app.geo import haversine_m

    best = None
    best_d = max_m
    for lm in LANDMARKS:
        d = haversine_m(lat, lon, lm["lat"], lm["lon"])
        if d <= best_d:
            best, best_d = lm, d
    return best
