# Kontrakt API Findini (v1)

Pełny, generowany kontrakt: [`openapi.json`](openapi.json) (36 ścieżek), interaktywnie: `GET /docs`.
Ten dokument opisuje zasady i najważniejsze operacje.

## Zasady ogólne
- Format: JSON (UTF‑8); daty ISO 8601 **ze strefą** (serwer zapisuje w UTC, aplikacja pokazuje w Europe/Warsaw). Czas zdarzenia (`occurred_from/to`) jest odróżniony od czasu publikacji (`published_at`).
- Uwierzytelnienie: `Authorization: Bearer fnd_…` — token sesji gościa z `POST /v1/sessions`. UUID zasobu nigdy nie zastępuje uwierzytelnienia; brak uprawnień do cudzego zasobu = **404** (nie ujawniamy istnienia).
- Błędy: `{"error": {"code": "…", "message": "komunikat po polsku", …}}`. Kody: 401 `session_required`, 403 `forbidden`/`banned`, 404 `not_found`, 409 (`item_reserved`, `already_claimed`, `invalid_state`…), 413/415 (zdjęcia), 422 (`validation_error` z listą `fields`, `outside_pilot`, `contact_data_in_public_text`, `bad_code` z `attempts_left`…), 429 `rate_limited`, 503 `ai_unavailable`.
- Nieznane pola w ciałach żądań są odrzucane (`extra=forbid`). Teksty są normalizowane (NFC, usuwanie znaków sterujących), mają limity długości.
- Paginacja: kursor (`next_cursor`) — keyset po (`published_at`,`id`) / (`dist`,`id`) / (`text_sim`,`id`), stabilna przy dopisywaniu nowych zgłoszeń.

## Publiczne (bez sesji)
| Metoda i ścieżka | Opis |
|---|---|
| `GET /health` | stan bazy, magazynu zdjęć i modelu AI |
| `GET /v1/meta` | kategorie z cechami (schemat formularzy), kolory, obszar pilotażu, punkty orientacyjne, retencja, wskazówki bezpieczeństwa, status AI |
| `GET /v1/reports` | wyszukiwanie: `kind`, `category`, `subtype`, `colors` (lista), `brand`, `q`, `lat`+`lon`+`radius_m` (100–25 000), `bbox`, `date_from`/`date_to` (≤ 1 rok), `sort` (relevance/newest/nearest), `cursor`, `limit` ≤ 50. Każdy wynik ma `match.reasons`/`warnings`, `distance_m` (od środka komórki, zaokrąglony). Brak wyników ⇒ `suggestions` |
| `GET /v1/reports/areas?bbox=` | agregacja po komórkach siatki dla mapy (liczba, rodzaje) — bez pojedynczych punktów |
| `GET /v1/reports/{id}` | szczegóły publiczne (właściciel dostaje dodatkowo `private`, liczniki roszczeń, stan indeksowania zdjęć) |
| `GET /v1/photos/{id}?size=thumb` | zdjęcie publiczne aktywnego zgłoszenia; inne — tylko uprawnieni |
| `POST /v1/search/parse` | asystent: zdanie → filtry + lista „zrozumiałem” |
| `GET /v1/places/suggest` | etykieta „okolice: …” dla punktu (z listy punktów orientacyjnych) |
| `GET /r/{id}` | strona WWW do udostępnienia (tylko pola publiczne) |

Publiczna reprezentacja zgłoszenia — **wyłącznie** te pola: `id, kind, status, category, category_label, title, description, attributes, colors, occurred_from, occurred_to, published_at, updated_at, area{lat, lon, radius_m, label, precision}, holding, holding_note, photos[], ai_indexed, distance_m, match, is_mine`. Test `test_public_payload_has_only_allowed_fields` pilnuje, by nic więcej nie wyciekło.

## Sesja i „moje”
| | |
|---|---|
| `POST /v1/sessions` | nowa sesja gościa (limit na IP) → `token`, pseudonim |
| `POST /v1/sessions/recover` `{code}` | odzyskanie na nowym telefonie: unieważnia stare sesje, wymienia kod |
| `DELETE /v1/sessions/current` | wylogowanie |
| `GET /v1/me` | pseudonim, statystyki (serduszka, zwroty), nieprzeczytane, czy jest kod odzyskiwania |
| `POST /v1/me/recovery-code` | nowy kod (pokazywany raz; serwer trzyma HMAC) |
| `GET /v1/me/reports`, `GET /v1/me/cases` | własne zgłoszenia (z danymi prywatnymi), sprawy w obu rolach |
| `GET /v1/me/updates?since=` | liczniki dla WorkManagera (bez treści) |
| `DELETE /v1/me` | usunięcie wszystkich danych gościa (kaskadowo + pliki) |

## Zgłoszenia i zdjęcia (z sesją)
| | |
|---|---|
| `POST /v1/photos` (multipart `file`, `purpose=report|evidence`) | walidacja dekodowaniem (JPEG/PNG/WEBP, ≤10 MB, ≤40 Mpx), ponowne kodowanie bez EXIF, miniatura; dla `report` — embedding i `suggestion` (kategoria, rodzaj, kolory, `confidence: clear|uncertain`, bez procentów) z limitem 4 s |
| `DELETE /v1/photos/{id}` | usunięcie własnego, niedołączonego zdjęcia |
| `POST /v1/search/by-photo` (multipart) | wyszukiwanie zdjęciem we własnej bazie; zdjęcie zapytania nie jest zapisywane; `no_convincing_match`, poziom `distinct|similar|related`, ostrzeżenie o innym kolorze |
| `POST /v1/reports` | publikacja (`kind`, `category`, `title`, `description`, `attributes`, `colors`, `occurred_from/to`, `location{lat, lon, accuracy_m, uncertainty_m, source}`, `area_label`, `holding`, `holding_note`, `secret_details`, `claim_question`, `photo_ids`) |
| `PATCH /v1/reports/{id}` | edycja (tylko właściciel, tylko aktywne/zarezerwowane, nie ukryte) |
| `DELETE /v1/reports/{id}` | wycofanie: zamyka roszczenia, usuwa zdjęcia |
| `POST /v1/reports/{id}/resolve` `{note}` / `/renew` | zamknięcie poza procesem roszczeń / odnowienie |
| `GET /v1/reports/{id}/matches` | dopasowania (tylko właściciel): `strong`, `possible`, `weak_count`, `notice` |
| `GET /v1/reports/{id}/claims` | roszczenia do mojego znaleziska |

Walidacja serwerowa m.in.: kategoria i cechy wg schematu, ≤3 kolory, przedział czasu ≤14 dni i nie w przyszłości, lokalizacja w obszarze pilotażu, brak telefonu/e‑maila/linków w polach publicznych, brak zdjęć przy dokumentach.

## Roszczenia i rozmowa
| | |
|---|---|
| `GET /v1/reports/{id}/claim-form` | pytanie weryfikacyjne (limit), czy można złożyć roszczenie |
| `POST /v1/reports/{id}/claims` | `{answer, proof_details, evidence_photo_ids[], lost_report_id}` — jedno na osobę i rzecz, limit dzienny |
| `GET /v1/claims/{id}` | sprawa; znalazca widzi swoją ukrytą cechę obok odpowiedzi; odbiorca widzi kod przekazania (po akceptacji); nikt nie dostaje „czy odpowiedź poprawna” |
| `POST /v1/claims/{id}/accept`, `/reject` `{note}` | decyzja znalazcy |
| `POST /v1/claims/{id}/withdraw` | wycofanie przez zgłaszającego |
| `POST /v1/claims/{id}/handover` `{code?}` | znalazca: z kodem ⇒ zwrot; bez kodu ⇒ czeka na potwierdzenie odbiorcy; 5 prób kodu |
| `POST /v1/claims/{id}/confirm-received` | odbiorca potwierdza odbiór |
| `POST /v1/claims/{id}/thanks` | serduszko (po zwrocie, raz) |
| `POST /v1/claims/{id}/block` | blokada kontaktu (zamyka sprawę, blokuje kolejne roszczenia) |
| `GET/POST /v1/claims/{id}/messages`, `POST /read` | rozmowa (≤1000 znaków, max 5 wiadomości z rzędu bez odpowiedzi) |
| `POST /v1/abuse-reports` | zgłoszenie nadużycia (zgłoszenie / sprawa / wiadomość — tylko widoczne dla zgłaszającego) |

## Moderacja (nagłówek `X-Admin-Token`)
`GET /v1/admin/abuse-reports?status=open`, `POST /v1/admin/abuse-reports/{id}/resolve` `{action: dismiss|hide_report|unhide_report|ban_guest, note}`; panel HTML: `GET /admin`.

## Limity (domyślne)
| Operacja | Na sesję | Na skrót IP |
|---|---|---|
| nowa sesja | — | 20/h |
| odzyskanie kodem | — | 8/h |
| publikacja | 10/doba | 30/doba |
| upload zdjęcia | 40/h | 120/h |
| roszczenie | 5/doba | 15/doba |
| pytanie weryfikacyjne | 30/h | 90/h |
| wiadomość | 60/h | 200/h |
| kod przekazania | 10/h (+ 5 prób na sprawę) | — |
| wyszukiwanie zdjęciem | 30/h | 90/h |
| zgłoszenie nadużycia | 20/doba | 60/doba |
| wyszukiwanie | — | 1200/h |
