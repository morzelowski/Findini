# Scenariusz demonstracji (~5 minut, dwie role)

**Role:** *Znalazca* (telefon/emulator A) i *Właściciel* (telefon/emulator B) + prowadzący przy rzutniku. Dwie niezależne instalacje = dwie niezależne sesje gościa.

## Przygotowanie (przed prezentacją, ~10 min)
1. `docker compose up -d --build`, `docker compose exec api python -m scripts.seed_demo --if-empty` (oznaczone dane demo: m.in. 7 podobnych czapek i 5 plecaków).
2. Zainstaluj `app-demoLocal.apk` (albo `app-debug.apk`) na A i B. Emulatory: `-camera-back emulated`, `adb emu geo fix 19.9195 50.0661` (Kampus AGH). Telefony: `adb reverse tcp:8080 tcp:8080` i w aplikacji *Ustawienia → Serwer* `http://localhost:8080/`.
3. Na A wgraj przykładowe zdjęcie przedmiotu do galerii (np. `adb push czapka.jpg /sdcard/Pictures/`) — albo przygotuj prawdziwy przedmiot do zdjęcia telefonem (np. czapkę członka zespołu).
4. Sprawdź `http://localhost:8080/health` (`ai.status = ready`).

## Przebieg
| Czas | Kto | Co pokazać | Co powiedzieć |
|---|---|---|---|
| 0:00 | prowadzący | slajd problemu | „Szukający zguby jest zestresowany i nie chce zakładać konta. Znalazca chce pomóc, nie ujawniając telefonu i adresu. A takich czapek w mieście są setki.” |
| 0:30 | A | **Zgłoś → Znalazłem coś → Aparat** (lub Galeria). Pojawia się „Podpowiedź z analizy zdjęcia: Odzież › czapka · biały” → *Zastosuj* | „Lokalny model na naszym serwerze podpowiada kategorię — bez kluczy i bez wysyłania zdjęcia do firm trzecich. To tylko sugestia.” |
| 1:00 | A | **Jestem na miejscu (GPS)** → przesunięcie pinezki → etykieta „okolice: Kampus AGH” → „Ostatnie 3 h” | „Rozróżniamy miejsce zdarzenia od tego, gdzie stoję teraz. Publicznie pokażemy tylko obszar ok. 500 m.” |
| 1:30 | A | Opis: marka; **ukryty szczegół** („pod daszkiem napis K.C.”) i pytanie → **Sprawdź**: sekcje *Publiczne* / *Prywatne* → **Opublikuj** | „Ukryty szczegół zna tylko prawdziwy właściciel. Sukces pokazujemy dopiero, gdy serwer zapisze zgłoszenie.” |
| 2:00 | B | Bez logowania: wpisz „zgubiłem białą czapkę przy AGH” → karta „Zrozumiałem tak…” → wynik z „dlaczego pasuje” → przełącz **Mapa** | „Asystent zamienia zdanie na filtry, które można poprawić. Na mapie kółka to przybliżone obszary, nie punkty.” |
| 2:40 | B | Szczegóły → **To moje — złóż prywatne roszczenie** → pytanie od znalazcy → odpowiedź → Wyślij | „Nie widzisz ukrytego szczegółu, a serwer nigdy nie mówi, czy odpowiedź jest poprawna — to utrudnia zgadywanie. Jedno roszczenie na osobę.” |
| 3:10 | A | **Moje sprawy → Roszczenia** → odpowiedź obok *Twojego ukrytego szczegółu* → **Akceptuj** → wiadomość „Jutro 12:00, hol A‑0?” | „O wydaniu decyduje człowiek, który ma przedmiot. AI ani dopasowanie tekstu nie oznaczają nikogo jako właściciela.” |
| 3:40 | B | Odpowiedź w czacie; pokaż **kod przekazania** i wskazówki bezpieczeństwa | „Kod pokazuje się przy spotkaniu w miejscu publicznym. Żadnych opłat, BLIK‑ów, adresów domowych.” |
| 4:05 | A | Wpisz kod → „Przedmiot wrócił do właściciela” | „Zwrot jest zatwierdzany atomowo — inne roszczenia do tej rzeczy zamykają się automatycznie; dwóch zwrotów nie da się potwierdzić (testy współbieżności).” |
| 4:20 | B | **Podziękuj znalazcy ❤** | „Serduszko tylko po zakończonym zwrocie i tylko raz — gest wdzięczności, nie ocena uczciwości.” |
| 4:35 | B | **Szukaj zdjęciem** (lupa z aparatem) — zdjęcie czapki z galerii | „Szukamy zdjęciem we własnej bazie. Uczciwie: przy wielu podobnych rzeczach model często wskazuje *podobny model w innym kolorze* — dlatego pokazujemy ostrzeżenie i nie podajemy procentów.” |
| 4:50 | prowadzący | slajd wyników (eksperyment, test obciążenia) i ograniczeń | „Recall@10 66% vs 2% losowo; p95 44 ms przy 50 sesjach; ograniczenia: zdjęcia katalogowe, brak testu na telefonie w terenie.” |

## Plan B
- **Brak sieci / mapy:** pokaż pasek „Jesteś offline” i zachowany szkic; ponów po przywróceniu sieci.
- **Aparat nie działa:** Galeria; aplikacja sama zaproponuje ją po 10 s.
- **AI niedostępne** (np. brak modelu): publikacja działa bez podpowiedzi; wyszukiwanie zdjęciem pokazuje czytelny komunikat — to też warto pokazać jako element odporności.
- **Zabrakło czasu na A:** użyj danych demo — kody odzyskiwania z wyjścia seeda (*Ustawienia → Przywróć dostęp kodem*) pozwalają działać jako demo‑znalazca, np. zaakceptować roszczenie do „Granatowej czapki z daszkiem”.

## Dodatkowe punkty (pytania komisji)
- *Moderacja:* zgłoszenie nadużycia z menu ⋮ w sprawie → panel `http://localhost:8080/admin`.
- *Prywatność lokalizacji:* test „wyszukiwania binarnego promienia” w `backend/tests/test_privacy_geo.py`.
- *Utrata telefonu:* *Ustawienia → Utwórz kod odzyskiwania* → na drugim urządzeniu *Przywróć dostęp*.
