# Raport z testów i weryfikacji

Bieżąca weryfikacja po rozszerzeniu na Polskę i zmianie modelu: [10.11.2026 — 71 testów, nowe APK i obciążenie](ZMIANY_2026_11_10.md). Poniżej pozostaje historyczny zapis z 07.11.2026.

Data: 7 listopada 2026. Wszystkie wyniki poniżej pochodzą z faktycznie uruchomionych poleceń; pozycje niezweryfikowane są wyraźnie oznaczone na końcu.

**Środowisko:** MacBook z Apple M5 (10 rdzeni, 32 GB RAM), macOS (Darwin 27.0), Docker Desktop 29.9 (VM: 10 CPU, 16 GB), PostgreSQL 17 + pgvector 0.8.7 + PostGIS 3.7, Python 3.12, emulator Android (obraz `google_apis` Android 12 / API 31, arm64, 1080×2400).

## 1. Backend — testy automatyczne (51/51 zaliczone)
`cd backend && .venv/bin/python -m pytest` — prawdziwa baza `findini_test` (od zera, migracje Alembic), prawdziwy model CLIP.

| Plik | Co sprawdza | Wynik |
|---|---|---|
| `test_unit.py` (12) | maszyny stanów; ranking: sygnały bez „%”, zdjęcie nie ukrywa niezgodności, „znalezione przed zgubieniem”, brak dopasowania, „mocne” wymaga cechy wyróżniającej, wyróżniające się zdjęcie; relacje kolorów; parser PL; walidacja cech; wykrywanie telefonów/e‑maili/linków; siatka i zaokrąglanie | ✅ |
| `test_flow.py` (8) | **pełna ścieżka na 3 sesjach** (zdjęcie z GPS w EXIF → publikacja → wyszukanie bez sesji → brak prywatnych pól i EXIF → roszczenie z dowodem → dowód niedostępny dla obcych → decyzja → czat → kod (błędny/poprawny) → zwrot → idempotencja → serduszko raz); zwrot bez kodu wymaga obu stron; zamykanie innych roszczeń i zamknięcie powiązanej zguby; cofnięcie akceptacji; edycja/usuwanie tylko własnych; odzyskanie kodem i utrata sesji; usunięcie danych; lista pól publicznych | ✅ |
| `test_privacy_geo.py` (5) | punkty w komórce = identyczna lokalizacja publiczna; **wyszukiwanie binarne promienia z 3 punktów odtwarza tylko środek komórki**, nie ukryty punkt; filtr promienia i sortowanie po odległości (PostGIS); odrzucenie spoza pilotażu; agregacja mapy bez punktów | ✅ |
| `test_concurrency_limits.py` (12) | **6 równoległych akceptacji → dokładnie 1**; równoległe kod+potwierdzenie → 1 zwrot, 5 równoległych serduszek → 1; limit roszczeń dziennych; brak roszczenia do własnej/zguby; blokada kodu po 5 próbach; anty‑spam czatu i blokada kontaktu; dane kontaktowe w treści publicznej; zakaz zdjęć dokumentów; walidacja plików (nie‑obraz, GIF, >10 MB, za małe); prywatność niepublikowanego zdjęcia; limit sesji na IP; endpointy prywatne bez tokenu | ✅ |
| `test_search_moderation.py` (9) | **paginacja kursorem bez duplikatów i braków** (3 sortowania); polska odmiana i ogonki; kolory pokrewne; podpowiedzi przy braku wyników (promień, daty); dopasowania z wyjaśnieniem i ostrzeżeniami, prywatność dopasowań; „brak przekonujących dopasowań”; nadużycia → auto‑ukrycie blokuje edycję, roszczenia, wyszukiwanie, zamyka sprawy; moderator banuje; zgłoszenie cudzej sprawy niemożliwe; meta + parser; healthcheck | ✅ |
| `test_ai.py` (5) | upload → sugestia bez procentów; wyszukiwanie zdjęciem (ta sama kopia — **test techniczny**) → „wyróżnia się”; brak przekonującego dopasowania; **brak modelu nie blokuje publikacji** (503 tylko dla wyszukiwania zdjęciem); indeksowanie w tle po powrocie modelu z zapisem wersji modelu | ✅ |

**Analiza statyczna:** `ruff check` (reguły E, F, W, I, B, UP, S, SIM, RUF) — 0 uwag; `ruff format --check` — zgodne.

## 2. Android — build, testy jednostkowe, lint
| Polecenie | Wynik |
|---|---|
| `./gradlew :app:assembleDebug` | ✅ `app-debug.apk` (69,7 MB) |
| `./gradlew :app:assembleRelease` (R8 + shrink zasobów) | ✅ `app-release.apk` (45,5 MB) |
| `./gradlew :app:assembleDemoLocal` (R8, lokalny serwer) | ✅ — zainstalowany na emulatorze: wyszukiwanie, asystent, mapa, szczegóły działają (sprawdzenie, że R8 nie psuje serializacji/Retrofit) |
| `./gradlew :app:testDebugUnitTest` | ✅ 3/3 (zgodność przymiotnika z rodzajem w automatycznym tytule, format odległości, UTC → Europe/Warsaw) |
| `./gradlew :app:lintDebug` | ✅ 0 błędów (6 błędów `StateFlowValueCalledInComposition` znalezionych i naprawionych); pozostały ostrzeżenia stylistyczne (`UseKtx`, `ModifierParameter`, `InsecureBaseConfiguration` — świadomie tylko w debug) |
| Zależności | wersje w `gradle/libs.versions.toml` + `app/gradle.lockfile` (358 artefaktów) |

## 3. Android — test na dwóch niezależnych urządzeniach (emulator ×2, prawdziwe API i baza)
Dwie instancje emulatora (`emulator-5554` = znalazca, `emulator-5556` = właściciel, osobne dane aplikacji ⇒ osobne sesje gościa), sterowane przez `adb`/uiautomator; zrzuty w [`zrzuty/`](zrzuty/).

| Krok | Urządzenie | Wynik |
|---|---|---|
| Odmowa uprawnienia aparatu → karta z alternatywą (galeria / bez zdjęcia / ustawienia) | A | ✅ [06](zrzuty/06_odmowa_aparatu.png) |
| Zgoda → podgląd CameraX → zdjęcie zapisane i wysłane | A | ✅ (z `-camera-back emulated`; patrz uwagi) |
| Zdjęcie z galerii (systemowy wybór plików) → upload → **podpowiedź AI „Odzież › czapka · biały”** | A | ✅ [07](zrzuty/07_zdjecie_sugestia_ai.png) |
| Uprawnienie lokalizacji → GPS ±5 m na mapie, koło niepewności, ręczne przesunięcie → „Źródło: ręcznie”, etykieta „okolice: Kampus AGH” | A | ✅ [08](zrzuty/08_gps_mapa.png) |
| Ukryty szczegół + pytanie, podsumowanie publiczne/prywatne, potwierdzenie zdjęć, publikacja po odpowiedzi serwera | A | ✅ [09](zrzuty/09_podsumowanie_publiczne_prywatne.png), [10](zrzuty/10_widok_wlasciciela_dopasowania.png) |
| Szukanie bez konta (asystent: „biala czapka starter”), szczegóły **bez ukrytej cechy i pytania** | B | ✅ [11](zrzuty/11_szczegoly_bez_konta.png) |
| Roszczenie (pytanie od znalazcy, odpowiedź, szczegóły) | B | ✅ |
| Znalazca widzi odpowiedź **obok swojej ukrytej cechy**, akceptuje, pisze | A | ✅ [12](zrzuty/12_ocena_roszczenia.png) |
| Odbiorca widzi wiadomość, odpowiada, widzi **kod przekazania** | B | ✅ [13](zrzuty/13_kod_przekazania_czat.png) |
| Znalazca wpisuje kod → „Przedmiot wrócił do właściciela” | A | ✅ [14](zrzuty/14_zwrot_zakonczony.png) |
| Podziękowanie (serduszko) → komunikat systemowy u obu | B | ✅ |
| Wyszukiwanie zdjęciem (galeria) | B | ✅ [15](zrzuty/15_wyszukiwanie_zdjeciem.png) — wynik „wyróżnia się” to czapka tego samego modelu w innym kolorze ⇒ dodano ostrzeżenie o kolorze |

## 4. Scenariusze awarii
| Scenariusz | Sposób | Wynik |
|---|---|---|
| Backend offline — wyszukiwanie | `docker compose stop api` | ✅ „Brak połączenia z serwerem Findini…” + „Spróbuj ponownie” |
| Backend offline — publikacja | publikacja w kreatorze | ✅ błąd w kreatorze, **brak fałszywego sukcesu**, szkic zachowany ([16](zrzuty/16_blad_zapisu_offline.png)) |
| Ponowienie zapisu | `docker compose start api` → „Opublikuj” | ✅ zapis na serwerze |
| Szkic po restarcie aplikacji | reinstalacja/ubicie procesu w trakcie kreatora | ✅ „Przywrócono szkic” z krokiem, zdjęciem i polami |
| Restart usług — trwałość | `docker compose down && up` | ✅ 23 zgłoszenia „znaleziono” przed i po; 22/22 zdjęcia publiczne serwowane |
| Utrata sesji | emulator z odtworzonym stanem dysku (brak tokenu) | ✅ pusty stan „Moje sprawy” z linkiem do odzyskania kodem; odzyskanie kodem testowane w API (`test_session_recovery_and_loss`) |
| Niedostępny model AI | test `test_ai_unavailable_does_not_block` + UI „Podpowiedzi AI są chwilowo niedostępne” | ✅ (API); komunikat w UI zaimplementowany, nie wywołany ręcznie na emulatorze |
| Brak internetu (tryb samolotowy) | `adb shell cmd connectivity airplane-mode enable` | ✅ pasek „Jesteś offline. Szkice zapisujemy na telefonie.”, błąd API z ponowieniem, kreator działa dalej ([17](zrzuty/17_brak_sieci_mapa.png)). Mapa wyświetliła się **z pamięci podręcznej MapLibre** — komunikat zastępczy „Mapa jest niedostępna” (przy błędzie wczytania stylu) zaimplementowany, ale w tym teście nie wystąpił |
| Aparat nie odpowiada | wirtualna kamera emulatora (`virtualscene`) zawieszała zapis | ✅ po poprawce: limit 10 s i komunikat „Aparat nie odpowiada… wybierz z galerii” |
| Kopia i odtworzenie | `scripts/backup.sh` → `pg_restore` do osobnej bazy | ✅ identyczne liczności (31 zgłoszeń, 28 zdjęć, 1 roszczenie, 7 wiadomości); archiwum: 56 plików (zdjęcia + miniatury) |

## 5. Test obciążenia (założenie pilota: 10 tys. zgłoszeń, ~50 równoległych sesji)
- **Dane:** osobna baza `findini_load` — 10 000 syntetycznych zgłoszeń wokół 10 punktów Krakowa, 1 000 gości, 3 002 zdjęcia z wektorami (prawdziwe embeddingi CLIP + szum), plus zgłoszenia tworzone w trakcie testu.
- **Konfiguracja:** API w kontenerze (ten sam obraz), PostgreSQL w kontenerze, generator `scripts/loadtest.py` (Python asyncio + httpx) **na tym samym komputerze**; limity żądań wyłączone (wszystkie sesje z jednego IP); emulatory wyłączone na czas pomiaru.
- **Profil (wagi):** wyszukiwanie 35% (losowo obszar, kategoria, kolor, tekst, data, 30% druga strona), mapa 12%, szczegóły 15%, miniatury 10%, asystent 5%, „moje sprawy” 6%, dopasowania 6%, publikacja 5%, wyszukiwanie zdjęciem 2% (pełna inferencja CLIP). „Czas myślenia” 0,2–1 s.

Odtworzenie (z katalogu `backend`):
```bash
.venv/bin/python -m scripts.loadtest_seed --db postgresql+psycopg://findini:findini-dev-password@localhost:5433/findini_load --photo-key "<storage_key istniejącego zdjęcia>"
docker run -d --name findini-load --network findini_default -p 8081:8080 \
  -e FINDINI_DATABASE_URL=postgresql+psycopg://findini:findini-dev-password@db:5432/findini_load \
  -e FINDINI_RATE_LIMITS_ENABLED=false -e FINDINI_WORKERS=1 \
  -v findini_photo-data:/data/photos -v "$PWD/../models:/models:ro" findini-api:1.0.0
.venv/bin/python -m scripts.loadtest --base http://localhost:8081 --users 50 --duration 120 --out ../docs/loadtest_wyniki_1worker.json
.venv/bin/python -m scripts.loadtest --base http://localhost:8081 --users 50 --duration 45 --think 0   # stres
```

**Realistyczny: 50 sesji × 120 s**
| | 1 proces API | 4 procesy API |
|---|---|---|
| Żądania / przepustowość | 9 791 / 81 rps | 9 868 / 82 rps |
| p50 / p95 / p99 (ogółem) | 8,9 / **43,9** / 83,7 ms | 7,8 / **32,8** / 69,7 ms |
| Błędy 5xx / sieć | **0** | **0** |
| p95 wyszukiwanie | 37,4 ms | 28,0 ms |
| p95 dopasowania | 59,5 ms | 55,7 ms |
| p95 wyszukiwanie zdjęciem (CLIP) | 107,3 ms | 80,6 ms |
| p95 publikacja | 27,0 ms | 10,9 ms |

**Stres (bez czasu myślenia), 50 sesji × 45 s**: 1 proces — 213 rps, p95 492 ms, 0 błędów; 4 procesy — 210 rps, p95 682 ms, 0 błędów.

**Interpretacja i ograniczenia pomiaru:** przy założonym ruchu pilota system ma duży zapas (p95 < 50 ms, zero błędów). Pułap ~210 rps **nie wzrósł przy 4 procesach**, co wskazuje na ograniczenie po stronie pomiaru (jednowątkowy generator w Pythonie na tej samej maszynie i proxy sieci Docker Desktop na macOS), a nie wiarygodną granicę API — tej granicy nie wyznaczyliśmy. Wyniki dotyczą jednego komputera deweloperskiego, sieci lokalnej i syntetycznych danych; **nie są dowodem skali produkcyjnej** (brak sieci komórkowej, TLS, innego sprzętu serwerowego, długotrwałego testu). Surowe wyniki: `loadtest_wyniki_*.json`.

## 6. Eksperyment AI
Patrz [EKSPERYMENT_AI.md](EKSPERYMENT_AI.md): Recall@10 = 0,66 (losowo 0,02) przy 511 zdjęciach podobnych rzeczy; bezwzględne progi nie odróżniają „braku dopasowania”, więc wprowadzono kryterium względne (precyzja ≈ 0,72); trafność podpowiedzi kategorii 0,81 (0,90 przy „wyraźnej”).

## 7. Błędy znalezione i naprawione w trakcie weryfikacji
- `FOR UPDATE` z łączeniem zewnętrznym (eager load) — blokady przepisane na `with_for_update(of=…)` + `populate_existing`.
- Bezwzględne progi podobieństwa dawały „przekonujące” wyniki dla nieistniejących rzeczy → kryterium przewagi top‑1.
- Poziom „mocne” bez cechy wyróżniającej (np. czapka zimowa vs z daszkiem) → wymóg cechy wyróżniającej.
- Format odległości „ok, 1,0 km”; tytuł „Biały czapka” → zgodność rodzaju; nieaktualna podpowiedź AI po usunięciu zdjęcia.
- Pasek „Dalej” zasłaniany przez klawiaturę → przeniesiony nad klawiaturę.
- Brak liczników na mapie (font stylu) i legenda zasłaniająca atrybucję OSM.
- Odczyt `StateFlow.value` w kompozycji (lint) — ekrany nie reagowały na doładowanie metadanych.
- Zawieszenie aparatu bez informacji → limit czasu i komunikat.

## 8. Czego NIE zweryfikowano (i jak to zrobić ręcznie)
| Obszar | Powód | Procedura |
|---|---|---|
| Fizyczny telefon (aparat, GPS w terenie, Wi‑Fi/LTE) | brak urządzenia w środowisku | zainstaluj `app-debug.apk`, `adb reverse tcp:8080 tcp:8080`, przejdź scenariusz z [DEMO.md](DEMO.md) na dwóch telefonach |
| Prawdziwa kamera tylna emulatora `virtualscene` | błędne znaczniki czasu klatek HAL emulatora na arm64 | użyto `-camera-back emulated`; na telefonie test jak wyżej |
| HTTPS z prawdziwą domeną (Caddy + Let's Encrypt) | brak domeny i publicznego IP | `docker compose --profile https up -d` na VPS z domeną; build `release` z `-Pfindini.releaseApiUrl=https://…` |
| Powiadomienia (Android 13+ uprawnienie, WorkManager w tle) | emulator API 31; brak czekania 30 min | na Android 13+: opublikuj zgubę, z drugiego urządzenia dodaj pasujące znalezisko, wymuś pracę: `adb shell cmd jobscheduler run -f pl.findini.app 0` lub odczekaj |
| TalkBack i duża czcionka | brak przejścia z czytnikiem w tym środowisku (zaimplementowano: opisy ikon, nagłówki sekcji, scalone opisy kart, live region statusu sprawy, kod czytany cyframi, cele ≥48 dp) | włącz TalkBack i rozmiar czcionki 200%, przejdź: wyszukiwanie → szczegóły → roszczenie → czat |
| Ciemny motyw | zaimplementowany, nie przejrzany na zrzutach | `adb shell cmd uimode night yes` |
| Komunikat „Mapa jest niedostępna” | mapa korzystała z pamięci podręcznej kafelków | wyczyść dane aplikacji, włącz tryb samolotowy, otwórz mapę |
| Panel `/admin` w przeglądarce | API przetestowane testami; HTML nieklikany | otwórz `/admin`, wklej token, rozpatrz zgłoszenie |
| Długotrwała praca (retencja po 60/180 dniach) | wymaga czasu | logika testowalna przez zmianę `FINDINI_REPORT_ACTIVE_DAYS`; zadanie `jobs.maintenance()` |
| Badania z użytkownikami | nie przeprowadzono | — (nie deklarujemy wyników) |
