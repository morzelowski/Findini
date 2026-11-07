"""Odtwarzalne, OZNACZONE dane demonstracyjne (Kraków).

- Wszystkie zgłoszenia mają w opisie znacznik „Zgłoszenie demonstracyjne” i należą do
  sesji gości z pseudonimem zaczynającym się od „Demo ·”. Nie podszywają się pod ruch użytkowników.
- Zdjęcia: Amazon Berkeley Objects (CC BY 4.0) — patrz scripts/demo_photos/ATTRIBUTION.md.
- Celowo kilka bardzo podobnych czapek/plecaków: pokazuje, że kategoria i kolor nie wystarczą.
- Pliki *_owner.jpg to inne ujęcie produktu (zgłoszenie zguby) — dopasowanie zdjęciem nie jest kopią.

Użycie (w kontenerze API):  python -m scripts.seed_demo [--if-empty]
Na końcu wypisuje kody odzyskiwania sesji demo — pozwalają w aplikacji „Przywrócić dostęp”
i działać jako demo-znalazca (np. zaakceptować roszczenie podczas prezentacji).
"""

from __future__ import annotations

import argparse
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.db import session_factory
from app.models import Guest, Photo, Report
from app.schemas import LocationIn, ReportCreate
from app.security import Actor, hash_recovery_code, new_recovery_code, now_utc
from app.services import ai, photos
from app.services.reports import create_report

PHOTOS = Path(__file__).parent / "demo_photos"
MARK = "\n\nZgłoszenie demonstracyjne (dane testowe)."

# (lat, lon) w pobliżu publicznych punktów orientacyjnych
AGH = (50.0661, 19.9195)
RYNEK = (50.0612, 19.9381)
KAZIMIERZ = (50.0522, 19.9441)
RUCZAJ = (50.0291, 19.9071)
DWORZEC = (50.0670, 19.9466)
UEK = (50.0690, 19.9541)
BLONIA = (50.0601, 19.9140)
NOWA_HUTA = (50.0718, 20.0369)
PK = (50.0716, 19.9428)

FINDERS = ["Demo · Życzliwa Wydra", "Demo · Uważny Borsuk", "Demo · Pomocna Sowa", "Demo · Spokojny Żuraw"]
OWNERS = ["Demo · Zmartwiony Jeż", "Demo · Roztargniony Lis"]

# kind, autor, kategoria, tytuł, opis, cechy, kolory, miejsce, etykieta, godziny temu (od, do), zdjęcie, prywatne
SPECS: list[dict[str, Any]] = [
    # --- wiele podobnych czapek
    dict(
        kind="found",
        who=0,
        cat="clothing",
        title="Granatowa czapka z daszkiem",
        desc="Leżała na ławce przy przystanku.",
        attrs={"subtype": "czapka", "brand": "Starter", "material": "syntetyk"},
        colors=["navy", "blue"],
        at=AGH,
        label="okolice: Kampus AGH",
        hours=(30, 28),
        photo="cap_navy_a",
        secret="Wewnątrz daszka napisane markerem „M.O.”",
        question="Co jest napisane wewnątrz daszka?",
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=1,
        cat="clothing",
        title="Granatowa czapka Starter",
        desc="Znaleziona w tramwaju linii 18.",
        attrs={"subtype": "czapka", "brand": "Starter"},
        colors=["navy"],
        at=DWORZEC,
        label="okolice: Dworzec Główny",
        hours=(50, 49),
        photo="cap_navy_b",
        secret="Brak metki z rozmiarem, zaplamiony daszek",
        question=None,
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=2,
        cat="clothing",
        title="Czarna czapka z daszkiem",
        desc="Na trawniku obok fontanny.",
        attrs={"subtype": "czapka", "brand": "Starter"},
        colors=["black"],
        at=BLONIA,
        label="okolice: Błonia",
        hours=(20, 19),
        photo="cap_black",
        secret="Regulacja z tyłu na ostatnim oczku",
        question="Jak ustawiony jest pasek regulacji?",
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=3,
        cat="clothing",
        title="Szara czapka z daszkiem",
        desc="Zostawiona w czytelni.",
        attrs={"subtype": "czapka"},
        colors=["gray"],
        at=PK,
        label="okolice: Politechnika Krakowska",
        hours=(6, 5),
        photo="cap_gray",
        secret="Mała dziurka przy szwie z lewej",
        question=None,
        holding="at_place",
        holding_note="Portiernia budynku głównego",
    ),
    dict(
        kind="found",
        who=0,
        cat="clothing",
        title="Beżowa czapka z daszkiem",
        desc="Pod stolikiem w kawiarni.",
        attrs={"subtype": "czapka"},
        colors=["beige"],
        at=KAZIMIERZ,
        label="okolice: Kazimierz (Plac Nowy)",
        hours=(72, 70),
        photo="cap_khaki",
        secret="Przypinka z rowerem na boku",
        question="Co jest przypięte do czapki?",
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=1,
        cat="clothing",
        title="Czarna czapka zimowa",
        desc="Dzianinowa, z wywinięciem.",
        attrs={"subtype": "czapka", "material": "dzianina"},
        colors=["black", "gray"],
        at=RYNEK,
        label="okolice: Rynek Główny",
        hours=(10, 9),
        photo="hat_black_beanie",
        secret="W środku metka z inicjałami A.Ł.",
        question="Co jest na metce w środku?",
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=2,
        cat="clothing",
        title="Czarna czapka uszatka",
        desc="Futrzana, leżała przy wejściu do galerii.",
        attrs={"subtype": "czapka"},
        colors=["black"],
        at=DWORZEC,
        label="okolice: Galeria Krakowska",
        hours=(96, 95),
        photo="hat_trapper_black",
        secret="Jedno ucho z przetartym zatrzaskiem",
        question=None,
        holding="office",
        holding_note="Biuro rzeczy znalezionych galerii",
    ),
    # --- plecaki
    dict(
        kind="found",
        who=3,
        cat="bags",
        title="Granatowy plecak",
        desc="Pusty, znaleziony przy wiacie rowerowej.",
        attrs={"subtype": "plecak", "material": "nylon"},
        colors=["navy"],
        at=RUCZAJ,
        label="okolice: Kampus UJ (Ruczaj)",
        hours=(26, 25),
        photo="backpack_navy",
        secret="W bocznej kieszeni bilet MPK i gumka do włosów",
        question="Co było w bocznej kieszeni?",
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=0,
        cat="bags",
        title="Czarny plecak z logo",
        desc="Został na sali wykładowej.",
        attrs={"subtype": "plecak"},
        colors=["black"],
        at=AGH,
        label="okolice: Kampus AGH",
        hours=(4, 3),
        photo="backpack_black_a",
        secret="Zepsuty zamek w przedniej kieszeni",
        question="Co jest nie tak z przednią kieszenią?",
        holding="at_place",
        holding_note="Portiernia budynku A-0",
    ),
    dict(
        kind="found",
        who=1,
        cat="bags",
        title="Czarny plecak typu rolltop",
        desc="Pod ławką na peronie.",
        attrs={"subtype": "plecak"},
        colors=["black"],
        at=DWORZEC,
        label="okolice: Dworzec Główny",
        hours=(40, 39),
        photo="backpack_black_b",
        secret="Brelok z muszelką przy zamku",
        question=None,
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=2,
        cat="bags",
        title="Szary plecak turystyczny",
        desc="Duży, z pokrowcem przeciwdeszczowym.",
        attrs={"subtype": "plecak"},
        colors=["gray"],
        at=NOWA_HUTA,
        label="okolice: Plac Centralny",
        hours=(120, 118),
        photo="backpack_gray",
        secret="Naszywka z flagą Norwegii",
        question="Jaka naszywka jest na plecaku?",
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=3,
        cat="bags",
        title="Granatowy plecak z czerwonymi wstawkami",
        desc="Szkolny, przy boisku.",
        attrs={"subtype": "plecak"},
        colors=["navy", "red"],
        at=BLONIA,
        label="okolice: Błonia",
        hours=(55, 54),
        photo="backpack_navy_red",
        secret="Imię wyszyte na szelce",
        question="Co jest wyszyte na szelce?",
        holding="with_finder",
    ),
    # --- portfele (bez zdjęć dokumentów)
    dict(
        kind="found",
        who=0,
        cat="wallets",
        title="Czarny portfel",
        desc="Skórzany, składany. Dokumentów nie fotografowałem.",
        attrs={"subtype": "portfel", "material": "skóra"},
        colors=["black"],
        at=UEK,
        label="okolice: Uniwersytet Ekonomiczny",
        hours=(8, 7),
        photo="wallet_black",
        secret="W środku legitymacja studencka i bilet miesięczny",
        question="Jakie dokumenty są w środku?",
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=1,
        cat="wallets",
        title="Brązowy portfel",
        desc="Przy kasie biletowej.",
        attrs={"subtype": "portfel", "material": "skóra"},
        colors=["brown"],
        at=DWORZEC,
        label="okolice: Dworzec Główny",
        hours=(14, 13),
        photo="wallet_brown",
        secret="Zdjęcie psa w przegródce",
        question="Co jest w przezroczystej przegródce?",
        holding="office",
        holding_note="Punkt informacji dworca",
    ),
    dict(
        kind="found",
        who=2,
        cat="wallets",
        title="Etui na karty",
        desc="Cienkie, czarne.",
        attrs={"subtype": "etui na karty"},
        colors=["black"],
        at=RYNEK,
        label="okolice: Rynek Główny",
        hours=(3, 2),
        photo="wallet_cardholder_black",
        secret="Karta biblioteczna i karta MPK",
        question="Jakie karty są w etui?",
        holding="with_finder",
    ),
    # --- elektronika
    dict(
        kind="found",
        who=3,
        cat="electronics",
        title="Słuchawki na kark",
        desc="Bezprzewodowe, czarne.",
        attrs={"subtype": "słuchawki"},
        colors=["black"],
        at=AGH,
        label="okolice: Kampus AGH",
        hours=(18, 17),
        photo="headphones_neckband",
        secret="Lewa słuchawka z naklejką gwiazdki",
        question="Co jest na lewej słuchawce?",
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=0,
        cat="electronics",
        title="Fioletowe słuchawki nauszne",
        desc="Dziecięce, w parku.",
        attrs={"subtype": "słuchawki"},
        colors=["purple", "white"],
        at=BLONIA,
        label="okolice: Błonia",
        hours=(60, 58),
        photo="headphones_purple",
        secret="Na pałąku napisane imię",
        question=None,
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=1,
        cat="electronics",
        title="Telefon w czarnym etui",
        desc="Wyłączony, nie przeglądałem zawartości.",
        attrs={"subtype": "telefon"},
        colors=["black"],
        at=KAZIMIERZ,
        label="okolice: Kazimierz",
        hours=(12, 11),
        photo="phonecase_black_heart",
        secret="Tapeta ekranu blokady: zdjęcie gór",
        question="Co jest na ekranie blokady?",
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=2,
        cat="electronics",
        title="Telefon w różowym etui w kwiaty",
        desc="Na siedzeniu w autobusie.",
        attrs={"subtype": "telefon"},
        colors=["pink"],
        at=NOWA_HUTA,
        label="okolice: Nowa Huta",
        hours=(36, 35),
        photo="phonecase_pink",
        secret="Pęknięty róg ekranu",
        question="Czy ekran jest uszkodzony? Gdzie?",
        holding="office",
        holding_note="Komisariat — Nowa Huta",
    ),
    # --- akcesoria i biżuteria
    dict(
        kind="found",
        who=3,
        cat="accessories",
        title="Czarne okulary przeciwsłoneczne",
        desc="Na murku przy Wiśle.",
        attrs={"subtype": "okulary"},
        colors=["black"],
        at=KAZIMIERZ,
        label="okolice: bulwary Wiślane",
        hours=(28, 27),
        photo="sunglasses_black",
        secret="Rysa na prawym szkle",
        question=None,
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=0,
        cat="jewelry",
        title="Srebrny pierścionek z oczkiem",
        desc="Na podłodze w szatni.",
        attrs={"subtype": "pierścionek", "material": "srebro"},
        colors=["silver"],
        at=RYNEK,
        label="okolice: Rynek Główny",
        hours=(22, 21),
        photo="ring_silver",
        secret="Grawer z datą wewnątrz obrączki",
        question="Co jest wygrawerowane w środku?",
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=1,
        cat="jewelry",
        title="Czarny zegarek sportowy",
        desc="Przy bieżni.",
        attrs={"subtype": "zegarek"},
        colors=["black"],
        at=BLONIA,
        label="okolice: Błonia",
        hours=(44, 43),
        photo="watch_black",
        secret="Ustawiony alarm na 6:15",
        question=None,
        holding="with_finder",
    ),
    dict(
        kind="found",
        who=2,
        cat="keys",
        title="Pęk kluczy z brelokiem misia",
        desc="Trzy klucze i pluszowy brelok. Bez zdjęcia, żeby nie pokazywać kształtu kluczy.",
        attrs={"subtype": "pęk kluczy", "key_count": 3, "keychain": "pluszowy miś"},
        colors=["brown"],
        at=UEK,
        label="okolice: Rondo Mogilskie",
        hours=(16, 15),
        photo=None,
        secret="Jeden klucz z niebieską nakładką",
        question="Jakiego koloru nakładkę ma jeden z kluczy?",
        holding="with_finder",
    ),
    # --- zgłoszenia zgub (właściciele)
    dict(
        kind="lost",
        who=0,
        cat="clothing",
        title="Zgubiłem granatową czapkę Starter",
        desc="Prawdopodobnie przy AGH albo w autobusie 144.",
        attrs={"subtype": "czapka", "brand": "Starter"},
        colors=["navy"],
        at=AGH,
        label="okolice: Kampus AGH",
        hours=(34, 29),
        photo="cap_navy_a_owner",
        secret="Napis M.O. w środku daszka",
        owner=True,
    ),
    dict(
        kind="lost",
        who=1,
        cat="bags",
        title="Granatowy plecak — zgubiony na Ruczaju",
        desc="Prosty, granatowy plecak, bez laptopa.",
        attrs={"subtype": "plecak"},
        colors=["navy"],
        at=RUCZAJ,
        label="okolice: Kampus UJ (Ruczaj)",
        hours=(28, 25),
        photo="backpack_navy_owner",
        secret="W kieszeni bilet MPK",
        owner=True,
    ),
    dict(
        kind="lost",
        who=0,
        cat="jewelry",
        title="Srebrny pierścionek zaręczynowy",
        desc="Bardzo cenny sentymentalnie.",
        attrs={"subtype": "pierścionek", "material": "srebro"},
        colors=["silver"],
        at=RYNEK,
        label="okolice: Rynek Główny",
        hours=(26, 20),
        photo="ring_silver_owner",
        secret="Grawer z datą 12.06",
        owner=True,
    ),
    dict(
        kind="lost",
        who=1,
        cat="electronics",
        title="Czarne słuchawki bezprzewodowe",
        desc="Na kark, zgubione między AGH a Czarnym Domem.",
        attrs={"subtype": "słuchawki"},
        colors=["black"],
        at=AGH,
        label="okolice: Kampus AGH",
        hours=(22, 16),
        photo="headphones_neckband_owner",
        secret="Naklejka gwiazdki na lewej",
        owner=True,
    ),
    dict(
        kind="lost",
        who=0,
        cat="keys",
        title="Klucze z brelokiem misia",
        desc="Trzy klucze do mieszkania i piwnicy.",
        attrs={"subtype": "pęk kluczy", "keychain": "miś"},
        colors=["brown"],
        at=UEK,
        label="okolice: Rondo Mogilskie",
        hours=(20, 15),
        photo=None,
        secret="Niebieska nakładka na kluczu do klatki",
        owner=True,
    ),
]


def _guest(db: Any, alias: str) -> tuple[Guest, str]:
    code = new_recovery_code()
    g = Guest(id=uuid.uuid4(), alias=alias, recovery_hash=hash_recovery_code(code), recovery_created_at=now_utc())
    db.add(g)
    db.flush()
    return g, code


def _photo(db: Any, owner: Guest, name: str) -> uuid.UUID:
    raw = (PHOTOS / f"{name}.jpg").read_bytes()
    img = photos.process_upload(raw)
    full = photos.store(img.full, "")
    thumb = full.replace(".jpg", "_t.jpg")
    photos._path_for(thumb).write_bytes(img.thumb)
    p = Photo(
        id=uuid.uuid4(),
        owner_id=owner.id,
        purpose="report",
        storage_key=full,
        thumb_key=thumb,
        width=img.width,
        height=img.height,
        bytes=len(img.full),
        sha256=img.sha256,
        embedding_status="pending",
    )
    eng = ai.engine()
    emb = eng.embed(img.image, timeout_s=30)
    if emb is not None:
        p.embedding = emb.tolist()
        p.embedding_model = eng.model_version
        p.embedding_status = "ready"
        p.ai_suggestion = eng.suggest(emb)
    db.add(p)
    db.flush()
    return p.id


def seed(if_empty: bool) -> None:
    db = session_factory()()
    try:
        if if_empty and (db.scalar(select(func.count()).select_from(Report)) or 0) > 0:
            print("Baza nie jest pusta — pomijam seed.")
            return
        ai.engine().load()
        finders = [_guest(db, a) for a in FINDERS]
        owners = [_guest(db, a) for a in OWNERS]
        db.commit()
        now = now_utc()
        n = 0
        for s in SPECS:
            g, _ = (owners if s.get("owner") else finders)[s["who"]]
            actor = Actor(guest_id=g.id, session_id=None, alias=g.alias)
            photo_ids = [_photo(db, g, s["photo"])] if s.get("photo") else []
            db.commit()
            h_from, h_to = s["hours"]
            body = ReportCreate(
                kind=s["kind"],
                category=s["cat"],
                title=s["title"],
                description=s["desc"] + MARK,
                attributes=s["attrs"],
                colors=s["colors"],
                occurred_from=now - timedelta(hours=h_from),
                occurred_to=now - timedelta(hours=h_to),
                location=LocationIn(
                    lat=s["at"][0], lon=s["at"][1], accuracy_m=15, uncertainty_m=0, source="gps" if n % 2 else "map"
                ),
                area_label=s["label"],
                holding=s.get("holding"),
                holding_note=s.get("holding_note"),
                secret_details=s.get("secret"),
                claim_question=s.get("question"),
                photo_ids=photo_ids,
            )
            create_report(db, actor, body)
            n += 1
        print(f"Utworzono {n} oznaczonych zgłoszeń demonstracyjnych.")
        print("Kody odzyskiwania sesji demo (Ustawienia → Przywróć dostęp kodem):")
        for g, code in finders + owners:
            print(f"  {g.alias:28s} {code}")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--if-empty", action="store_true")
    seed(ap.parse_args().if_empty)
