# Findini

**Aplikacja na Androida do zgłaszania znalezionych przedmiotów i odnajdywania zgub** — z prawdziwym backendem, bazą danych, aparatem, GPS, wyszukiwaniem zdjęciem i bezpieczną ścieżką zwrotu.

Zespół: Krzysztof Czaplicki, Aleksandra Łabęda, Mateusz Orzełowski · Pilotaż: **Kraków** (założenie projektowe, konfigurowalne).

<p>
<img src="docs/zrzuty/01_start.png" width="180"> <img src="docs/zrzuty/02b_asystent_lista.png" width="180"> <img src="docs/zrzuty/09_podsumowanie_publiczne_prywatne.png" width="180"> <img src="docs/zrzuty/12_ocena_roszczenia.png" width="180"> <img src="docs/zrzuty/13_kod_przekazania_czat.png" width="180">
</p>

## Co działa

| Obszar | Zaimplementowane |
|---|---|
| Szukanie bez konta | Lista + mapa (MapLibre/OpenFreeMap) z przybliżonymi obszarami, filtry: rodzaj, kategoria/rodzaj, kolor (z kolorami pokrewnymi), czas zdarzenia, obszar (GPS jednorazowo, punkty orientacyjne, promień), tekst odporny na polską odmianę i brak ogonków (pg_trgm + unaccent), stabilna paginacja kursorem, „dlaczego pasuje” przy każdym wyniku, podpowiedzi przy braku wyników. |
| Asystent wyszukiwania | Zdanie po polsku („zgubiłem czarną czapkę wczoraj przy AGH”) → edytowalne filtry. Działa na regułach (bez LLM i bez kluczy) — opisane uczciwie jako reguły. |
| Zgłoszenie „Znalazłem/Zgubiłem” | Kreator 4 kroków: zdjęcia (CameraX w aplikacji / Photo Picker / bez zdjęcia), miejsce zdarzenia (GPS z niepewnością + ręczna korekta na mapie + punkty orientacyjne), przedział czasu, gdzie jest teraz przedmiot, cechy zależne od kategorii, **ukryty szczegół** i pytanie weryfikacyjne, podgląd „co publiczne / co prywatne”. Szkic zapisuje się lokalnie i przetrwa błąd sieci i restart aplikacji. Edycja, odnowienie, zamknięcie, usunięcie. |
| AI (lokalne, bez kluczy) | CLIP ViT-B/32 w ONNX Runtime na serwerze: **wyszukiwanie zdjęciem we własnej bazie**, sygnał w dopasowaniach, **podpowiedź kategorii/rodzaju/koloru** (do zatwierdzenia). Indeksowanie w tle z ponawianiem, stan widoczny w aplikacji, AI niedostępne ⇒ reszta działa. [Eksperyment](docs/EKSPERYMENT_AI.md) na 511 zdjęciach podobnych rzeczy. |
| Dopasowania zguba ↔ znalezisko (wyróżnik) | Automatyczni kandydaci z poziomami „mocne / możliwe” i sygnałami (kategoria, kolor, marka, odległość, czas, zdjęcie) oraz **ostrzeżeniami o niezgodnościach**; „brak przekonujących dopasowań”; okresowe sprawdzanie (WorkManager) i lokalne powiadomienie. |
| Roszczenie → zwrot | Prywatne roszczenie (odpowiedź + opcjonalne zdjęcie‑dowód widoczne tylko dla znalazcy), znalazca porównuje z ukrytym szczegółem i decyduje, czat przypisany do sprawy, **jednorazowy kod przekazania**, potwierdzenie obu stron, zamknięcie pozostałych roszczeń, serduszko (raz). Odporność na współbieżność (blokady + unikalny indeks częściowy). |
| Zaufanie i nadużycia | Blokada kontaktu, zgłoszenie nadużycia (auto‑ukrycie po 3 zgłoszeniach), panel moderacji `/admin`, wskazówki bezpiecznego przekazania, odrzucanie telefonów/e‑maili/linków w treściach publicznych, brak zdjęć dokumentów, limity żądań (sesja + skrót IP). |
| Prywatność | Publicznie tylko komórka siatki ~500 m (odległości i filtr „w promieniu” też od środka komórki); dokładny punkt, ukryta cecha, pytanie, dowody i rozmowy — tylko w osobnych tabelach i endpointach z autoryzacją; EXIF usuwany na telefonie i na serwerze; token w Android Keystore; kod odzyskiwania (serwer trzyma tylko HMAC); usunięcie wszystkich danych; retencja. |
| Udostępnianie | Link `…/r/{id}` — strona WWW z danymi publicznymi do wrzucenia na grupę uczelni/osiedla (odpowiedź na „mało zgłoszeń”). |

Szczegóły: [architektura](docs/ARCHITEKTURA.md) · [API](docs/API.md) · [model zagrożeń](docs/MODEL_ZAGROZEN.md) · [prywatność i retencja](docs/PRYWATNOSC_I_RETENCJA.md) · [raport z testów](docs/RAPORT_TESTOW.md) · [eksperyment AI](docs/EKSPERYMENT_AI.md) · [scenariusz demo](docs/DEMO.md) · [materiał na poster](docs/POSTER.md).

## Wymagania

| Narzędzie | Wersja użyta i sprawdzona |
|---|---|
| Docker + Docker Compose | Docker 29.9, Compose v5.6 (Docker Desktop, macOS arm64) |
| Python (tylko testy/skrypty poza kontenerem) | 3.12 |
| JDK do buildu Androida | 17+ (sprawdzone: JBR 25 z Android Studio 2026.1) |
| Android SDK | platforma 37 (compileSdk 37), build‑tools 36.0.0; minSdk 26, targetSdk 36 |
| Gradle / AGP / Kotlin | Gradle 9.8.2 (wrapper), AGP 9.5.1, Kotlin 2.4.21 (wbudowany w AGP) |
| Backend | FastAPI 0.162.2, SQLAlchemy 2.1.8, Alembic 1.20.1, psycopg 3.3.8, ONNX Runtime 1.31.1, Pillow 13 — pełna lista z sumami: `backend/requirements.txt` |
| Baza | PostgreSQL 17 + pgvector 0.8.7 + PostGIS 3.7 (obraz budowany z `infra/db`) |

Zużycie: obrazy Docker ~1,5 GB, model AI ~0,5 GB, cache Gradle ~3 GB.

## Szybki start (backend)

```bash
cp .env.example .env            # uzupełnij FINDINI_SERVER_SECRET i FINDINI_ADMIN_TOKEN
```

```bash
python3 backend/scripts/download_model.py
```

```bash
docker compose up -d --build
```

```bash
curl http://localhost:8080/health
```

- Model: `Xenova/clip-vit-base-patch32` (licencja MIT), rewizja przypięta, pliki sprawdzane SHA‑256, ~420 MB w `models/`. Bez modelu API działa, a funkcje AI zgłaszają niedostępność.
- Migracje Alembic uruchamiają się automatycznie przy starcie kontenera (`alembic upgrade head` — idempotentne).
- Dokumentacja interaktywna API: http://localhost:8080/docs, kontrakt: [`docs/openapi.json`](docs/openapi.json).
- Dane i zdjęcia są w wolumenach `findini_db-data` i `findini_photo-data` — przetrwają restart i `docker compose down` (bez `-v`).

**Dane demonstracyjne** (oznaczone, 28 zgłoszeń w Krakowie, zdjęcia z ABO na licencji CC BY 4.0):

```bash
docker compose exec api python -m scripts.seed_demo --if-empty
```

Skrypt wypisuje kody odzyskiwania sesji demo — w aplikacji: *Ustawienia → Przywróć dostęp kodem*, aby działać jako demo‑znalazca/właściciel.

## Aplikacja Android

### Emulator (domyślnie)
Build debug łączy się z `http://10.0.2.2:8080/` (to adres komputera widziany z emulatora — `localhost` emulatora to sam emulator).

```bash
cd android && ./gradlew :app:assembleDebug
```

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Lokalizację emulatora ustaw na Kraków (zgłoszenia spoza obszaru pilotażu są odrzucane):

```bash
adb emu geo fix 19.9195 50.0661
```

Aparat w emulatorze: uruchom z `-camera-back emulated` (kamera `virtualscene` na Apple Silicon zwracała błędne klatki — patrz raport testów).

### Telefon fizyczny
Telefon nie widzi `localhost` komputera. Dwie możliwości:
1. **USB + adb reverse** (najprościej):
   ```bash
   adb reverse tcp:8080 tcp:8080
   ```
   i w aplikacji *Ustawienia → Serwer (wersja deweloperska)* wpisz `http://localhost:8080/`.
2. **Ta sama sieć Wi‑Fi**: w *Ustawienia → Serwer* wpisz `http://ADRES-IP-KOMPUTERA:8080/` (API nasłuchuje na `0.0.0.0:8080`, sprawdź zaporę). Można też zbudować z adresem: `./gradlew :app:assembleDebug -Pfindini.apiUrl=http://192.168.1.20:8080/`.

HTTP bez szyfrowania jest dozwolony **tylko** w buildach `debug` i `demoLocal` (`src/debug/res/xml/network_security_config.xml`). Build `release` akceptuje wyłącznie HTTPS.

### Warianty buildu i APK
| Wariant | Polecenie | Przeznaczenie |
|---|---|---|
| `debug` | `./gradlew :app:assembleDebug` | rozwój, emulator/LAN, HTTP |
| `demoLocal` | `./gradlew :app:assembleDemoLocal` | kod jak release (R8), lokalny serwer HTTP — do prezentacji |
| `release` | `./gradlew :app:assembleRelease -Pfindini.releaseApiUrl=https://twoja-domena/` | HTTPS, R8; podpisany kluczem debug (do celów projektu — produkcyjny klucz trzymaj poza repo) |

Zbudowane i sprawdzone pliki: `android/app/build/outputs/apk/{debug,demoLocal,release}/` (debug ~70 MB, release/demoLocal ~45 MB — natywne biblioteki MapLibre dla 4 ABI). Domyślny `release` wskazuje na zastępczy `https://findini.example.org/` — przed dystrybucją podaj prawdziwy adres.

## HTTPS poza środowiskiem deweloperskim
Profil `https` uruchamia Caddy z automatycznym certyfikatem Let's Encrypt (wymaga domeny wskazującej na serwer i otwartych portów 80/443):

```bash
docker compose --profile https up -d
```

W `.env`: `FINDINI_ENV=prod`, `FINDINI_DOMAIN`, `FINDINI_PUBLIC_BASE_URL=https://…`, `FINDINI_TRUST_PROXY_HEADERS=true`, `FINDINI_FORWARDED_ALLOW_IPS=*`, `API_BIND=127.0.0.1`. W trybie `prod` API odmówi startu bez silnego sekretu i adresu HTTPS. *Profil HTTPS nie był testowany na publicznej domenie (brak domeny w środowisku projektu).*

## Testy i jakość

```bash
docker compose up -d db
```

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

```bash
.venv/bin/python -m pytest -q
```

```bash
.venv/bin/ruff check app tests scripts && .venv/bin/ruff format --check app tests scripts
```

```bash
cd android && ./gradlew :app:testDebugUnitTest :app:lintDebug
```

Testy integracyjne tworzą od zera bazę `findini_test` w kontenerze `db` (PostGIS+pgvector) i uruchamiają migracje. Wyniki: [docs/RAPORT_TESTOW.md](docs/RAPORT_TESTOW.md).

**Eksperyment AI** (pobiera ~1,3 tys. zdjęć ABO do `data/abo`):

```bash
cd backend && .venv/bin/python -m scripts.ai_experiment download && .venv/bin/python -m scripts.ai_experiment run
```

**Test obciążenia** (10 tys. zgłoszeń w osobnej bazie `findini_load`, 50 sesji):

```bash
cd backend && .venv/bin/python -m scripts.loadtest_seed --db postgresql+psycopg://findini:findini-dev-password@localhost:5433/findini_load
```

Następnie uruchom drugą instancję API na tę bazę (polecenie w raporcie testów) i:

```bash
.venv/bin/python -m scripts.loadtest --base http://localhost:8081 --users 50 --duration 120
```

## Kopia zapasowa i odtworzenie

```bash
./scripts/backup.sh
```

```bash
./scripts/restore.sh backups/RRRRMMDD-HHMMSS
```

Kopia = `pg_dump` (format custom) + archiwum wolumenu zdjęć + sumy SHA‑256. Zawiera dane prywatne — przechowuj zaszyfrowaną. Odtworzenie nadpisuje dane i wymaga potwierdzenia.

## Moderacja
Ustaw `FINDINI_ADMIN_TOKEN` (min. 24 znaki), otwórz http://localhost:8080/admin i wklej token. Akcje: odrzuć zgłoszenie nadużycia, ukryj/przywróć ogłoszenie, zablokuj autora (unieważnia sesje i ukrywa jego ogłoszenia). Ukrycie blokuje też roszczenia, zdjęcia i dopasowania — nie tylko usuwa kartę z listy.

## Zależności zewnętrzne, licencje, koszty

| Element | Dostawca / licencja | Klucz / koszt | Zachowanie przy awarii |
|---|---|---|---|
| Mapa | MapLibre Android 13.7.1 (BSD‑2), kafelki **OpenFreeMap** (styl Positron), dane © współtwórcy OpenStreetMap (ODbL) — atrybucja w przycisku „i” na mapie | bez klucza i opłat; przy dużym ruchu rozważ własny serwer kafelków | komunikat „Mapa niedostępna”, lista i punkty orientacyjne działają, ręczny wybór miejsca też |
| Geokodowanie | nie używamy zewnętrznego — lista publicznych punktów orientacyjnych Krakowa w kodzie (`app/domain/nlquery.py`) | — | — |
| AI | CLIP ViT‑B/32 (OpenAI, MIT) w eksporcie ONNX `Xenova/clip-vit-base-patch32` (MIT), lokalnie | bez kluczy i opłat; CPU ~20–30 ms/zdjęcie | wyszukiwanie zdjęciem zwraca 503 z czytelnym komunikatem; podpowiedzi znikają; indeksowanie dokończy się w tle |
| Krój pisma | Plus Jakarta Sans (SIL OFL 1.1) | — | — |
| Zdjęcia demo/eksperymentu | Amazon Berkeley Objects (CC BY 4.0) — `backend/scripts/demo_photos/ATTRIBUTION.md` | — | — |

Findini nie korzysta z Google Maps, Firebase ani płatnych API. Brak integracji z Google Lens, AirTag/Bluetooth — lokalizacja zgłoszenia to wskazane miejsce zdarzenia, nie śledzenie przedmiotu.

## Rozwiązywanie problemów
- **Aplikacja: „Brak połączenia z serwerem”** — sprawdź `curl http://localhost:8080/health`; w emulatorze adres to `10.0.2.2`, na telefonie patrz sekcja „Telefon fizyczny”.
- **„Findini działa obecnie pilotażowo w obszarze: Kraków”** — ustaw lokalizację emulatora na Kraków albo przesuń pinezkę; obszar zmienisz zmiennymi `FINDINI_PILOT_*`.
- **AI „missing_model”** w `/health` — uruchom `download_model.py`; katalog `models/` jest montowany do kontenera tylko do odczytu.
- **Pobieranie modelu: błąd certyfikatu SSL** (Python z python.org na macOS) — skrypt użyje `certifi`, jeśli jest zainstalowany (`pip install certifi`), albo uruchom „Install Certificates.command”.
- **Obraz `postgis/postgis` nie działa na arm64** — dlatego baza jest budowana z `pgvector/pgvector` + PostGIS z repozytorium PGDG (`infra/db/Dockerfile`).
- **Czarny podgląd aparatu w emulatorze** — uruchom emulator z `-camera-back emulated`; aplikacja po 10 s bez odpowiedzi aparatu proponuje galerię.
- **429 „Zbyt wiele prób”** — limity działają też na IP; w testach lokalnych z jednego komputera można je wyłączyć `FINDINI_RATE_LIMITS_ENABLED=false` (nigdy w produkcji).

## Struktura repozytorium
```
android/            aplikacja (Kotlin, Jetpack Compose, Material 3)
backend/app/        API FastAPI: routers/, services/ (zgłoszenia, roszczenia, zdjęcia, AI, zadania), domain/ (stany, dopasowania, kategorie, parser)
backend/alembic/    migracje
backend/tests/      testy jednostkowe i integracyjne (prawdziwy PostgreSQL)
backend/scripts/    pobieranie modelu, seed demo, eksperyment AI, test obciążenia
infra/              obraz bazy, konfiguracja Caddy (HTTPS)
scripts/            backup.sh, restore.sh
docs/               dokumentacja, wyniki testów, zrzuty ekranu
```

## Ograniczenia (skrót — pełna lista w raporcie testów)
- Nie sprawdzono na fizycznym telefonie ani na prawdziwej domenie z HTTPS; testy Android to emulator (Android 12, arm64).
- AI ocenione na zdjęciach katalogowych; zdjęcia „z ulicy” będą trudniejsze. Podobieństwo nie dowodzi własności — dlatego decyduje znalazca.
- Utrata telefonu bez zapisanego kodu odzyskiwania = utrata dostępu do zgłoszeń (świadomy kompromis braku kont).
- Projekt nie jest gotowy produkcyjnie: brak audytu bezpieczeństwa, testów z użytkownikami i obsługi prawnej (regulamin, RODO) — opisane w dokumentacji jako założenia, nie gwarancje.
