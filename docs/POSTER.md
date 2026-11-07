# Findini — materiał na poster i prezentację

**Findini: od zguby do bezpiecznego zwrotu — bez kont, z poszanowaniem prywatności**
Krzysztof Czaplicki · Aleksandra Łabęda · Mateusz Orzełowski

## Problem
- Osoba, która coś zgubiła, działa w stresie i nie chce zakładać konta, żeby sprawdzić, czy ktoś znalazł jej rzecz.
- Znalazca chce pomóc szybko, bez ujawniania telefonu, adresu i tożsamości.
- Podobnych rzeczy jest dużo (setki czarnych czapek) — kategoria i kolor nie wystarczą, a ogłoszenia w grupach społecznościowych bywają przynętą dla oszustów.

## Rozwiązanie
Aplikacja na Androida z prawdziwym backendem. Pilotaż: Kraków.
1. **Szukaj od razu, bez konta:** lista i mapa z przybliżonymi obszarami, filtry, asystent „zdanie → filtry”, wyszukiwanie zdjęciem.
2. **Zgłoś w minutę:** zdjęcie (aparat/galeria), miejsce zdarzenia (GPS z ręczną korektą), czas, cechy; podpowiedź kategorii z AI; widać, co jest publiczne, a co prywatne.
3. **Dopasowania z wyjaśnieniem** (wyróżnik): „ta sama kategoria · kolor czarny · ok. 300 m · zgodny czas”, ostrzeżenia o niezgodnościach, „brak przekonujących dopasowań” zamiast fałszywej pewności; powiadomienia o nowych kandydatach.
4. **Bezpieczny zwrot:** ukryty szczegół zna tylko właściciel → prywatne roszczenie → decyzja znalazcy → czat w sprawie → jednorazowy kod przekazania w miejscu publicznym → potwierdzenie → ❤.

## Architektura
`Android (Kotlin, Compose, CameraX, MapLibre)` ⇄ `HTTPS` ⇄ `FastAPI` → `PostgreSQL + PostGIS + pgvector` · `wolumen zdjęć (bez EXIF)` · `CLIP ViT‑B/32 w ONNX (lokalnie)` — całość w `docker compose`; HTTPS przez Caddy.

Kluczowe decyzje: publiczna lokalizacja = środek komórki ~500 m (zapytania nie zdradzają punktu); dane prywatne w osobnej tabeli; sesja gościa z tokenem w Android Keystore i kodem odzyskiwania; maszyna stanów zwrotu z blokadami i unikalnym indeksem (brak podwójnego wydania).

## Wyniki (zmierzone)
| | |
|---|---|
| Testy automatyczne backendu | **51/51** (prawdziwa baza; w tym współbieżność, prywatność API i plików, geoprywatność, limity) |
| Test E2E na 2 niezależnych urządzeniach (emulator) | pełna ścieżka zdjęcie → wyszukanie bez konta → roszczenie → decyzja → czat → kod → zwrot → ❤ ✅ |
| Wyszukiwanie zdjęciem, 511 zdjęć podobnych rzeczy (ABO) | Recall@1 **35%**, Recall@10 **66%** (losowo 2%) |
| „Brak przekonującego dopasowania” | kryterium przewagi: precyzja **0,72** (progi bezwzględne zawodziły) |
| Podpowiedź kategorii | **81%** trafności (90% przy oznaczeniu „wyraźna”) |
| Obciążenie: 10 tys. zgłoszeń, 50 sesji | **81 żądań/s, p95 44 ms, 0 błędów** (1 proces API, laptop) |

## Wnioski
- AI pomaga **zawęzić** poszukiwania, ale nie rozpoznaje egzemplarza — w 2/3 przypadków na pierwszym miejscu jest *podobna* rzecz. Dlatego Findini łączy zdjęcie z miejscem, czasem, cechami i ukrytym szczegółem, a decyzję zostawia człowiekowi.
- Uczciwy komunikat („nic się nie wyróżnia”) jest ważniejszy niż wysoki wynik podobieństwa.
- Prywatność trzeba projektować w danych i API (siatka, osobne tabele, autoryzacja plików), a nie tylko ukrywać w interfejsie.

## Ograniczenia
- Testy na emulatorze; brak testu na telefonach w terenie i z HTTPS na publicznej domenie.
- Eksperyment AI na zdjęciach katalogowych — zdjęcia z ulicy będą trudniejsze.
- Bez konta utrata telefonu bez kodu odzyskiwania = utrata dostępu.
- Brak badań z użytkownikami i analizy prawnej (RODO, regulamin).

## Zrzuty ekranu do posteru
`docs/zrzuty/02b_asystent_lista.png`, `03_mapa.png`, `09_podsumowanie_publiczne_prywatne.png`, `12_ocena_roszczenia.png`, `13_kod_przekazania_czat.png`, `14_zwrot_zakonczony.png`, `15_wyszukiwanie_zdjeciem.png`.
