# Prywatność, retencja i moderacja

> To opis rozwiązań technicznych w projekcie, a nie polityka prywatności ani opinia prawna. Przed publicznym wdrożeniem potrzebny jest regulamin, informacja o przetwarzaniu danych i analiza RODO.

## Jakie dane zbieramy i po co
| Dane | Widoczność | Cel | Gdzie |
|---|---|---|---|
| Token sesji gościa (losowy) | tylko telefon; serwer ma skrót SHA‑256 | dostęp do własnych zgłoszeń i spraw bez konta | Keystore / `sessions` |
| Pseudonim („Życzliwy Jeż 27”) | tylko właściciel | rozpoznanie własnej sesji | `guests` |
| Kod odzyskiwania (opcjonalny) | pokazany raz; serwer: HMAC | przeniesienie dostępu na nowy telefon | `guests.recovery_hash` |
| Opis, kategoria, cechy, kolory, czas zdarzenia, obszar ~500 m, zdjęcia (bez EXIF), „gdzie jest teraz” | publiczne | znalezienie właściciela | `reports`, `photos` |
| Dokładny punkt, dokładność GPS, źródło (GPS/mapa) | tylko autor | korekta zgłoszenia, sugestia etykiety | `report_private` |
| Ukryty szczegół, pytanie weryfikacyjne | autor (pytanie: także osoba składająca roszczenie) | weryfikacja roszczeń | `report_private` |
| Odpowiedź, szczegóły, zdjęcie‑dowód | znalazca i autor roszczenia | ocena roszczenia | `claims`, `photos(purpose=evidence)` |
| Wiadomości | uczestnicy sprawy | ustalenie przekazania | `messages` |
| Skrót IP (HMAC, 24 znaki) | nikt | limity nadużyć | `rate_buckets` (do 2 dób) |
| Zgłoszenia nadużyć | moderator | moderacja | `abuse_reports` |

Nie zbieramy: imienia, e‑maila, telefonu, adresu, identyfikatora urządzenia, lokalizacji w tle. Lokalizacja telefonu jest pobierana jednorazowo, tylko po naciśnięciu „Jestem na miejscu (GPS)” lub „Moja okolica”, i służy jako punkt startowy do korekty.

## Model AI a dane
Zdjęcia zgłoszeń są analizowane **lokalnie na serwerze Findini** (bez wysyłki do zewnętrznych usług). Wektory zdjęć są przechowywane z identyfikatorem i wersją modelu; zmiana modelu powoduje ponowne indeksowanie. Zdjęcia dowodów nigdy nie są analizowane ani indeksowane. Zdjęcie użyte do „szukaj zdjęciem” jest przetwarzane w pamięci i nie jest zapisywane. Ukryte/usunięte zgłoszenia są pomijane w wyszukiwaniu wektorowym (filtr w zapytaniu), a ich zdjęcia nie są indeksowane.

## Retencja (domyślne wartości, zmienne `FINDINI_*`)
| Element | Czas | Mechanizm |
|---|---|---|
| Aktywne zgłoszenie | 60 dni, potem `expired` (znika z wyszukiwania; można odnowić) | zadanie porządkowe co 10 min |
| Zgłoszenia zakończone / wycofane / wygasłe (z danymi prywatnymi, roszczeniami, rozmowami, dowodami, zdjęciami) | usunięcie po 180 dniach od ostatniej zmiany | j.w. (kaskada w bazie + pliki) |
| Zdjęcia zgłoszenia wycofanego | usuwane natychmiast | `DELETE /v1/reports/{id}` |
| Zdjęcia niewykorzystane (wgrane, ale niedołączone) | 24 h | zadanie porządkowe |
| Sesje unieważnione | 30 dni; nieużywane — 365 dni | zadanie porządkowe |
| Liczniki limitów (skróty IP) | 2 doby | zadanie porządkowe |
| Kopie zapasowe | poza aplikacją — zalecane: rotacja 14–30 dni, szyfrowanie | `scripts/backup.sh` |

**Usunięcie własnych danych**: *Ustawienia → Usuń wszystkie moje dane* (`DELETE /v1/me`) usuwa gościa wraz z zgłoszeniami, danymi prywatnymi, zdjęciami (pliki), roszczeniami, rozmowami i sesjami. Rozmowy z drugą stroną znikają także dla niej (jest o tym informacja przed usunięciem). Dane mogą jeszcze istnieć w kopiach zapasowych do końca ich rotacji.

## Anonimowość — ograniczenia (komunikowane w aplikacji)
- Brak konta oznacza, że **dostęp jest przypisany do telefonu**. Usunięcie aplikacji lub utrata telefonu bez kodu odzyskiwania = utrata dostępu (zgłoszenia pozostaną do wygaśnięcia). Nie mamy innego sposobu potwierdzenia tożsamości — i celowo go nie udajemy.
- Odzyskanie kodem unieważnia sesję na starym telefonie.
- Druga strona sprawy może się dowiedzieć, kim jesteś, jeśli sam to ujawnisz w rozmowie lub przy spotkaniu.
- Serwer technicznie widzi adres IP połączenia (jak każdy serwer); w bazie zapisujemy tylko skrót z sekretem, na krótko.

## Moderacja
1. Każdy użytkownik może zgłosić ogłoszenie, sprawę lub wiadomość (powód + opis).
2. Trzy zgłoszenia od różnych osób ⇒ ogłoszenie automatycznie ukryte do decyzji moderatora: znika z wyszukiwania i mapy, zdjęcia i dopasowania przestają działać, otwarte sprawy są zamykane, autor nie może edytować.
3. Moderator (panel `/admin`, token w zmiennej środowiskowej) widzi zgłoszony obiekt — nie całe rozmowy — i może: odrzucić zgłoszenie, ukryć/przywrócić ogłoszenie, zablokować autora (unieważnia sesje, ukrywa jego ogłoszenia).
4. Zmiany stanów zapisują się w `audit_events` (bez treści prywatnych).
