"""Kategorie, cechy zależne od kategorii i paleta kolorów.

To jedno źródło prawdy: serwer waliduje według tego schematu, a aplikacja Android
pobiera go z GET /v1/meta i buduje z niego formularze i filtry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.errors import invalid


@dataclass(frozen=True)
class Attr:
    key: str
    label: str
    type: str  # select | text | number
    options: list[str] = field(default_factory=list)
    max_len: int = 40
    hint: str | None = None
    # Czy zgodność tej cechy jest silnym sygnałem dopasowania (np. marka, rodzaj).
    strong: bool = False


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    icon: str
    attrs: list[Attr]
    # Podpowiedzi dla modelu (zero-shot, po angielsku — CLIP był trenowany na angielskim).
    prompts: dict[str, str] = field(default_factory=dict)
    photo_allowed: bool = True
    tip: str | None = None


COLORS: list[tuple[str, str, str]] = [
    # klucz, nazwa PL, hex (dla UI)
    ("black", "czarny", "#1F1F1F"),
    ("white", "biały", "#F5F5F5"),
    ("gray", "szary", "#8E8E8E"),
    ("silver", "srebrny", "#C0C4C8"),
    ("gold", "złoty", "#C9A227"),
    ("brown", "brązowy", "#7A4E2D"),
    ("beige", "beżowy", "#D8C3A0"),
    ("red", "czerwony", "#C62828"),
    ("pink", "różowy", "#EC8DB5"),
    ("orange", "pomarańczowy", "#EF7D22"),
    ("yellow", "żółty", "#F2C522"),
    ("green", "zielony", "#3C8D4A"),
    ("blue", "niebieski", "#2F6FD0"),
    ("navy", "granatowy", "#1D2B5A"),
    ("purple", "fioletowy", "#7B4FB3"),
    ("multi", "wielokolorowy", "#888888"),
]
COLOR_KEYS = [c[0] for c in COLORS]
COLOR_PL = {c[0]: c[1] for c in COLORS}
# Angielskie nazwy do promptów modelu
COLOR_EN = {
    "black": "black",
    "white": "white",
    "gray": "gray",
    "silver": "silver",
    "gold": "gold",
    "brown": "brown",
    "beige": "beige",
    "red": "red",
    "pink": "pink",
    "orange": "orange",
    "yellow": "yellow",
    "green": "green",
    "blue": "blue",
    "navy": "navy blue",
    "purple": "purple",
}

MATERIALS_CLOTH = ["bawełna", "wełna", "polar", "dzianina", "skóra", "syntetyk", "jeans", "inny"]
MATERIALS_BAG = ["materiał", "skóra", "ekoskóra", "nylon", "plastik", "inny"]

CATEGORIES: list[Category] = [
    Category(
        key="electronics",
        label="Elektronika",
        icon="devices",
        attrs=[
            Attr(
                "subtype",
                "Rodzaj",
                "select",
                [
                    "telefon",
                    "laptop",
                    "tablet",
                    "słuchawki",
                    "ładowarka / powerbank",
                    "smartwatch",
                    "aparat",
                    "pendrive / dysk",
                    "inne",
                ],
                strong=True,
            ),
            Attr("brand", "Marka", "text", hint="np. Apple, Dell, Samsung", strong=True),
            Attr("model", "Model", "text", hint="jeśli widoczny"),
            Attr("case", "Etui / obudowa", "text", hint="np. przezroczyste etui z naklejką"),
        ],
        prompts={
            "telefon": "a photo of a smartphone",
            "laptop": "a photo of a laptop computer",
            "tablet": "a photo of a tablet computer",
            "słuchawki": "a photo of headphones or earbuds",
            "ładowarka / powerbank": "a photo of a phone charger or power bank",
            "smartwatch": "a photo of a smartwatch",
            "aparat": "a photo of a digital camera",
        },
        tip="Nie włączaj urządzenia i nie przeglądaj jego zawartości. Numer seryjny wpisz tylko w polu prywatnym.",
    ),
    Category(
        key="keys",
        label="Klucze",
        icon="key",
        attrs=[
            Attr(
                "subtype",
                "Rodzaj",
                "select",
                ["pęk kluczy", "pojedynczy klucz", "kluczyk samochodowy", "karta / brelok do drzwi"],
                strong=True,
            ),
            Attr("key_count", "Liczba kluczy", "number"),
            Attr("keychain", "Brelok", "text", hint="np. pluszowy miś, logo klubu", strong=True),
        ],
        prompts={
            "pęk kluczy": "a photo of a bunch of keys on a key ring",
            "pojedynczy klucz": "a photo of a single metal key",
            "kluczyk samochodowy": "a photo of a car key fob",
            "karta / brelok do drzwi": "a photo of an access card or key fob tag",
        },
    ),
    Category(
        key="clothing",
        label="Odzież",
        icon="checkroom",
        attrs=[
            Attr(
                "subtype",
                "Rodzaj",
                "select",
                ["czapka", "szalik", "rękawiczki", "kurtka", "bluza / sweter", "inne"],
                strong=True,
            ),
            Attr("material", "Materiał", "select", MATERIALS_CLOTH),
            Attr("brand", "Marka", "text", strong=True),
            Attr("pattern", "Wzór", "select", ["gładki", "paski", "krata", "logo / napis", "wzór"]),
            Attr("size", "Rozmiar", "text", max_len=10),
        ],
        prompts={
            "czapka": "a photo of a knitted hat or beanie or cap",
            "szalik": "a photo of a scarf",
            "rękawiczki": "a photo of gloves",
            "kurtka": "a photo of a jacket",
            "bluza / sweter": "a photo of a sweater or hoodie",
        },
    ),
    Category(
        key="bags",
        label="Torby i plecaki",
        icon="backpack",
        attrs=[
            Attr(
                "subtype",
                "Rodzaj",
                "select",
                ["plecak", "torebka", "torba na laptopa", "torba sportowa", "walizka", "worek / saszetka"],
                strong=True,
            ),
            Attr("brand", "Marka", "text", strong=True),
            Attr("material", "Materiał", "select", MATERIALS_BAG),
        ],
        prompts={
            "plecak": "a photo of a backpack",
            "torebka": "a photo of a handbag or purse",
            "torba na laptopa": "a photo of a laptop bag",
            "torba sportowa": "a photo of a sports duffel bag",
            "walizka": "a photo of a suitcase",
            "worek / saszetka": "a photo of a small pouch or waist bag",
        },
    ),
    Category(
        key="wallets",
        label="Portfele i dokumenty",
        icon="wallet",
        attrs=[
            Attr(
                "subtype",
                "Rodzaj",
                "select",
                [
                    "portfel",
                    "etui na karty",
                    "dowód osobisty",
                    "legitymacja",
                    "prawo jazdy",
                    "paszport",
                    "karta płatnicza",
                    "inne dokumenty",
                ],
                strong=True,
            ),
            Attr("material", "Materiał", "select", ["skóra", "ekoskóra", "materiał", "plastik", "inny"]),
            Attr("brand", "Marka", "text"),
        ],
        prompts={
            "portfel": "a photo of a wallet",
            "etui na karty": "a photo of a card holder",
        },
        photo_allowed=True,
        tip=(
            "Nie publikuj zdjęć ani danych z dokumentów (imię, numer, adres). Opisz je ogólnie. "
            "Znaleziony dowód osobisty możesz też oddać w urzędzie gminy lub na policji."
        ),
    ),
    Category(
        key="jewelry",
        label="Biżuteria i zegarki",
        icon="diamond",
        attrs=[
            Attr(
                "subtype",
                "Rodzaj",
                "select",
                ["pierścionek", "naszyjnik", "bransoletka", "kolczyki", "zegarek", "inne"],
                strong=True,
            ),
            Attr("material", "Materiał", "select", ["złoto", "srebro", "stal", "koraliki", "inny"]),
            Attr("brand", "Marka", "text"),
        ],
        prompts={
            "pierścionek": "a photo of a ring",
            "naszyjnik": "a photo of a necklace",
            "bransoletka": "a photo of a bracelet",
            "kolczyki": "a photo of earrings",
            "zegarek": "a photo of a wristwatch",
        },
    ),
    Category(
        key="accessories",
        label="Akcesoria",
        icon="eyeglasses",
        attrs=[
            Attr(
                "subtype",
                "Rodzaj",
                "select",
                ["okulary", "parasol", "bidon / kubek", "książka / zeszyt", "zabawka", "inne"],
                strong=True,
            ),
            Attr("brand", "Marka", "text"),
        ],
        prompts={
            "okulary": "a photo of eyeglasses or sunglasses",
            "parasol": "a photo of an umbrella",
            "bidon / kubek": "a photo of a water bottle or thermos mug",
            "książka / zeszyt": "a photo of a book or notebook",
            "zabawka": "a photo of a toy or plush teddy",
        },
    ),
    Category(
        key="other",
        label="Inne",
        icon="category",
        attrs=[
            Attr("subtype", "Co to jest?", "text", max_len=40, strong=True),
        ],
        prompts={},
    ),
]

CATEGORY_BY_KEY = {c.key: c for c in CATEGORIES}


def meta_payload() -> dict[str, Any]:
    return {
        "categories": [
            {
                "key": c.key,
                "label": c.label,
                "icon": c.icon,
                "photo_allowed": c.photo_allowed,
                "tip": c.tip,
                "attributes": [{k: v for k, v in asdict(a).items() if k != "strong"} for a in c.attrs],
            }
            for c in CATEGORIES
        ],
        "colors": [{"key": k, "label": pl, "hex": hx} for k, pl, hx in COLORS],
    }


def validate_category(key: str) -> Category:
    cat = CATEGORY_BY_KEY.get(key)
    if cat is None:
        raise invalid("bad_category", "Nieznana kategoria.")
    return cat


def validate_attributes(category: str, attrs: dict[str, Any] | None) -> dict[str, Any]:
    cat = validate_category(category)
    out: dict[str, Any] = {}
    if not attrs:
        return out
    allowed = {a.key: a for a in cat.attrs}
    for k, v in attrs.items():
        a = allowed.get(k)
        if a is None:
            raise invalid("bad_attribute", f"Cecha „{k}” nie pasuje do kategorii {cat.label}.")
        if v is None or v == "":
            continue
        if a.type == "number":
            try:
                n = int(v)
            except (TypeError, ValueError) as e:
                raise invalid("bad_attribute", f"Cecha „{a.label}” musi być liczbą.") from e
            if not 0 <= n <= 999:
                raise invalid("bad_attribute", f"Cecha „{a.label}” ma nieprawidłową wartość.")
            out[k] = n
        elif a.type == "select":
            if not isinstance(v, str) or v not in a.options:
                raise invalid("bad_attribute", f"Nieprawidłowa wartość cechy „{a.label}”.")
            out[k] = v
        else:
            if not isinstance(v, str):
                raise invalid("bad_attribute", f"Cecha „{a.label}” musi być tekstem.")
            s = " ".join(v.split())
            if len(s) > a.max_len:
                raise invalid("bad_attribute", f"Cecha „{a.label}” może mieć maks. {a.max_len} znaków.")
            if s:
                out[k] = s
    return out


def validate_colors(colors: list[str] | None) -> list[str]:
    if not colors:
        return []
    uniq: list[str] = []
    for c in colors:
        if c not in COLOR_PL:
            raise invalid("bad_color", "Nieznany kolor.")
        if c not in uniq:
            uniq.append(c)
    if len(uniq) > 3:
        raise invalid("bad_color", "Wybierz maksymalnie 3 kolory.")
    return uniq


def strong_attr_keys(category: str) -> list[str]:
    cat = CATEGORY_BY_KEY.get(category)
    return [a.key for a in cat.attrs if a.strong] if cat else []


def attr_label(category: str, key: str) -> str:
    cat = CATEGORY_BY_KEY.get(category)
    if cat:
        for a in cat.attrs:
            if a.key == key:
                return a.label
    return key
