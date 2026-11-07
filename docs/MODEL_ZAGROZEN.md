# Model zagrożeń (zwięzły)

Zakres: aplikacja Android, API, baza, magazyn zdjęć, model AI, panel moderacji. Aktorzy: osoba szukająca, znalazca, oszust (fałszywy właściciel lub fałszywy znalazca), stalker/ciekawski, spamer, osoba z dostępem do kopii/logów.

| # | Zagrożenie | Przykład | Zabezpieczenie w Findini | Ryzyko szczątkowe |
|---|---|---|---|---|
| 1 | Odtworzenie dokładnego miejsca | seria zapytań „w promieniu” z wielu punktów, analiza dystansu | publicznie tylko środek komórki ~500 m; filtr i dystans liczone od środka; dystans zaokrąglany; test wyszukiwania binarnego | obszar ~500 m bywa wystarczający, by rozpoznać budynek — dlatego miejsce przekazania ustalane w rozmowie |
| 2 | Wyciek danych prywatnych przez API | serializacja całego obiektu, pole „zapomniane” w odpowiedzi | jawna lista pól publicznych; osobna tabela `report_private`; testy sprawdzają zestaw pól i brak tekstu ukrytej cechy | błąd przy dodawaniu nowych pól — testy pilnują listy |
| 3 | Fałszywy właściciel / masowe zgadywanie | wysyłanie wielu odpowiedzi na pytanie | jedno roszczenie na osobę i rzecz (także po odrzuceniu), limity dzienne na sesję i IP, brak informacji „poprawna/niepoprawna”, decyzja człowieka, ostrzeżenie „odpowiedź nie jest dowodem tożsamości” | nowe sesje z innych sieci — limity IP ograniczają, nie eliminują; zgadujący z wiedzą z publicznego opisu |
| 4 | Fałszywy znalazca (ogłoszenie‑przynęta, wyłudzenie opłaty) | „oddam telefon po przelewie 50 zł” | brak płatności w produkcie; blokada telefonów/e‑maili/linków w treści publicznej; komunikaty „Findini nigdy nie wymaga opłat”; zgłoszenie nadużycia → auto‑ukrycie po 3 zgłoszeniach; blokada kontaktu; moderacja | oszust może prosić o pieniądze w czacie — ostrzeżenia, zgłoszenia i blokada |
| 5 | Przejęcie cudzej sprawy / IDOR | zgadnięcie UUID roszczenia, podmiana `report_id` | autoryzacja przy każdym odczycie i zmianie (uczestnik sprawy / właściciel); 404 zamiast 403; testy obcej sesji | — |
| 6 | Kradzież tokenu sesji | kopia zapasowa telefonu, logi | token w Android Keystore (AES‑GCM, klucz nieeksportowalny), wyłączony backup; na serwerze tylko SHA‑256; tokenów nie logujemy; HTTPS w release | zainfekowany telefon z rootem |
| 7 | Przejęcie dostępu kodem odzyskiwania | zgadywanie kodu | 100 bitów entropii, HMAC z sekretem serwera, limit 8 prób/h na IP, kod jednorazowy (wymiana po użyciu) | kod zapisany przez użytkownika w niebezpiecznym miejscu |
| 8 | Metadane w zdjęciach | GPS w EXIF zdjęcia z domu | ponowne kodowanie na telefonie i na serwerze (bez EXIF/XMP), oryginał nieprzechowywany; test na zdjęciu z GPS | treść zdjęcia (adres na kopercie, twarz) — ostrzeżenie i checkbox przed publikacją; brak automatycznego maskowania |
| 9 | Dostęp do dowodów i prywatnych zdjęć | znajomość URL zdjęcia dowodu | pliki tylko przez endpoint z autoryzacją, nagłówki `private, no-store`; dowody nie trafiają do AI ani indeksu (`CHECK` w bazie) | uczestnik może zrobić zrzut ekranu |
| 10 | Złośliwe pliki / DoS uploadem | „bomba dekompresyjna”, 100 MB | limit 10 MB, ≤40 Mpx, dekodowanie Pillow z limitem, odrzucanie nieobsługiwanych formatów, limit uploadów | — |
| 11 | Nadużycie kosztownych operacji AI | masowe wyszukiwanie zdjęciem | limity na sesję i IP, pula 2 wątków i kolejka max 8, timeout, model lokalny (brak kosztu zewnętrznego) | spowolnienie AI przy ataku — reszta API działa |
| 12 | Spam i nękanie w czacie | dziesiątki wiadomości | max 5 wiadomości z rzędu bez odpowiedzi, limit godzinowy, blokada kontaktu, zgłoszenie wiadomości (moderator widzi tylko zgłoszoną wiadomość) | — |
| 13 | Podwójne wydanie przedmiotu / wyścigi | dwie akceptacje równocześnie, podwójny „zwrot” | blokady wierszy w stałej kolejności, unikalny indeks częściowy, idempotencja; testy współbieżności | — |
| 14 | Treści ogłoszeń sterujące AI | „zignoruj instrukcje…” w opisie | model obrazu nie interpretuje tekstu ogłoszeń; asystent działa na regułach (brak LLM) | przy przyszłym LLM: tylko walidowany schemat filtrów |
| 15 | Wyciek przez logi | treść wiadomości w logach | logujemy metodę, szablon ścieżki, kod i czas — bez nagłówków, zapytań, ciał | logi platformy (Docker) — brak treści do wycieku |
| 16 | Wyciek kopii zapasowej | skradziony `backups/` | dokumentacja: szyfrowanie i ograniczony dostęp; sumy kontrolne | brak automatycznego szyfrowania kopii (do wdrożenia na serwerze docelowym) |
| 17 | Moderator nadużywa uprawnień | przegląd cudzych rozmów | panel pokazuje tylko obiekt zgłoszenia (np. jedną wiadomość), token tylko w pamięci karty | brak audytu działań moderatora poza tabelą `audit_events` |
| 18 | Ruch nieszyfrowany | podsłuch w Wi‑Fi | release: tylko HTTPS (Network Security Config); HTTP wyłącznie w `debug`/`demoLocal`; Caddy z TLS | — |

## Granica zaufania
Klient (aplikacja) **nie** jest granicą zaufania: wszystkie reguły (stany, uprawnienia, walidacja, limity, prywatność lokalizacji) są egzekwowane na serwerze; aplikacja tylko je odzwierciedla.

## Czego Findini nie obiecuje
- Pewności, że osoba odbierająca jest właścicielem — dowodzą tego najwyżej szczegóły znane właścicielowi, a decyduje znalazca.
- Wykrywania przedmiotu z GPS telefonu, sieci tagów ani rozpoznawania „tego samego egzemplarza” przez AI.
- Pełnej zgodności z prawem (RODO, regulamin, przepisy o rzeczach znalezionych) — wymaga analizy prawnej przed wdrożeniem.
